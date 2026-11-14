// Run from frontend/: node scripts/verify-fixture-overrides.mjs
// Uses Node and the project's installed TypeScript compiler; no backend calls.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = dirname(dirname(fileURLToPath(import.meta.url)));
const cache = join(frontend, "node_modules", ".cache");
mkdirSync(cache, { recursive: true });
const compiled = mkdtempSync(join(cache, "fixture-overrides-"));
const require = createRequire(import.meta.url);

try {
  execFileSync(process.execPath, [
    join(frontend, "node_modules/typescript/bin/tsc"),
    "lib/types.ts", "lib/fixtures.ts", "lib/api.ts", "--outDir", compiled,
    "--module", "commonjs", "--target", "ES2022", "--skipLibCheck", "--esModuleInterop", "--strict",
  ], { cwd: frontend, stdio: "inherit" });
  const { api, apiSources, ApiError, setPrincipal } = require(join(compiled, "api.js"));
  const { resetFixtures, tamperFixtureAudit } = require(join(compiled, "fixtures.js"));
  for (const method of Object.keys(apiSources)) apiSources[method] = "fixture";

  const originals = (evaluation) => ({
    recommendation: evaluation.recommendation,
    rationale: evaluation.rationale,
    checks: evaluation.checks.map((check) => ({
      id: check.criterion_id, result: check.result, evidence: check.evidence,
      explanation: check.explanation, facts: check.facts,
    })),
  });
  const check = (evaluation, criterionId) => evaluation.checks.find((item) => item.criterion_id === criterionId);
  const row = (rows, txnId) => rows.find((item) => item.txn_id === txnId);
  const blocked = (request, status, code) => assert.rejects(request,
    (error) => error instanceof ApiError && error.status === status && error.code === code);
  async function fresh() {
    await resetFixtures();
    setPrincipal("ana");
    await api.evaluatePending();
    return (await api.transactions()).transactions;
  }

  // a: Judgment override, protected refresh, approval snapshot and learning.
  let rows = await fresh();
  let evaluation = await api.evaluation(row(rows, "TXN-0003").eval_id);
  let before = originals(evaluation);
  const payrollReason = "Payroll customers spike at month-end, that's normal.";
  await blocked(api.decide(evaluation.eval_id, "approved"), 409, "checks_not_cleared");
  evaluation = await api.overrideCheck(evaluation.eval_id, "C-04", "pass", payrollReason);
  assert.deepEqual(originals(evaluation), before);
  assert.equal(evaluation.effective_recommendation, "pass");
  const overriddenReference = await api.references(evaluation.eval_id, "C-04");
  assert.equal(overriddenReference.check.result, "no_pass");
  assert.equal(overriddenReference.check.effective_result, "pass");
  assert.equal(overriddenReference.check.override.by, "ana");
  assert(!(await api.audit()).events.some((event) => event.event === "memory.created"));
  const protectedBatch = await api.evaluatePending(true);
  assert(!protectedBatch.evaluated.some((item) => item.txn_id === "TXN-0003"));
  const protectedIndividual = await api.evaluate("TXN-0003", true);
  assert.equal(protectedIndividual.eval_id, evaluation.eval_id);
  assert.deepEqual(originals(protectedIndividual), before);
  const a = await api.decide(evaluation.eval_id, "approved");
  assert.equal(a.decision.agreed_with_agent, false);
  assert.equal(a.decision.effective_recommendation, "pass");
  assert.deepEqual(a.decision.overrides, [{
    criterion_id: "C-04", kind: "judgment", from: "no_pass", to: "pass", reason: payrollReason, via: "panel",
  }]);
  assert.equal(a.memory_created.filter((item) => item.kind === "adjustment").length, 1);
  const refreshed = await api.evaluatePending(true);
  assert.deepEqual(refreshed.evaluated.filter((item) => item.changed).map((item) => item.txn_id), ["TXN-0004"]);
  rows = (await api.transactions()).transactions;
  const learned = await api.references(row(rows, "TXN-0004").eval_id, "C-04");
  assert.equal(learned.adjustments[0].author_name, "Ana");
  assert.equal(learned.adjustments[0].source_txn_id, "TXN-0003");
  assert.equal(learned.check.result, "pass");
  await blocked(api.overrideCheck(evaluation.eval_id, "C-04", null), 409, "already_decided");
  console.log("a PASS: payroll override → approve → learning → TXN-0004 pass; originals, snapshot and refresh protection verified");

  // b: Hard and judgment overrides share the reviewer audit path.
  rows = await fresh();
  evaluation = await api.evaluation(row(rows, "TXN-0002").eval_id);
  before = originals(evaluation);
  await assert.rejects(api.decide(evaluation.eval_id, "approved"), (error) => {
    assert(error instanceof ApiError);
    assert.equal(error.status, 409);
    assert.equal(error.code, "checks_not_cleared");
    assert.deepEqual(error.blocking_checks, ["C-04", "W-01"]);
    assert.equal(error.message, "Clear C-04 and W-01 before approving.");
    return true;
  });
  evaluation = await api.overrideCheck(evaluation.eval_id, "W-01", "pass", "Verified beneficiary address from source documents.");
  evaluation = await api.overrideCheck(evaluation.eval_id, "C-04", "flag", "Documented one-off shipment explains the larger payment.");
  assert.deepEqual(originals(evaluation), before);
  const b = await api.decide(evaluation.eval_id, "approved");
  assert.equal(b.decision.overrides.length, 2);
  assert.equal(b.decision.agreed_with_agent, false);
  assert.equal(b.memory_created.filter((item) => item.kind === "adjustment").length, 1);
  assert(b.memory_created.find((item) => item.kind === "precedent").text.includes("W-01"));
  assert(b.memory_created.find((item) => item.kind === "adjustment").text.includes("Documented one-off shipment"));
  const bEvents = (await api.audit("TXN-0002")).events;
  assert.equal(bEvents.filter((event) => event.event === "check.overridden" && event.actor.id === "ana" && event.actor.type === "human" && event.actor.on_behalf_of === null).length, 2);
  assert(bEvents.some((event) => event.event === "memory.created" && event.detail.kind === "adjustment" && event.detail.criterion_id === "C-04"));
  assert(!bEvents.some((event) => event.event === "memory.created" && event.detail.kind === "adjustment" && event.detail.criterion_id === "W-01"));
  console.log("b PASS: W-01 and C-04 overridden and approved; human audit actors; generic judgment learning; hard override precedent only");

  // c: The comment requirement follows the effective recommendation.
  rows = await fresh();
  evaluation = await api.evaluation(row(rows, "TXN-0001").eval_id);
  await blocked(api.decide(evaluation.eval_id, "rejected"), 422, "invalid_request");
  const c = await api.decide(evaluation.eval_id, "rejected", "Customer requested cancellation.");
  assert.equal(c.transaction_status, "rejected");
  assert.equal(c.decision.agreed_with_agent, false);
  assert.equal((await api.decide(row(rows, "TXN-0002").eval_id, "rejected")).transaction_status, "rejected");
  console.log("c PASS: rejecting effective pass requires comment; rejecting effective no-pass does not");

  // d: Amount limits gate both writes, and a supervisor can retry.
  rows = await fresh();
  evaluation = await api.evaluation(row(rows, "TXN-0005").eval_id);
  before = originals(evaluation);
  await blocked(api.overrideCheck(evaluation.eval_id, "C-04", "flag", "Supervisor review requested."), 403, "gate_denied");
  await blocked(api.decide(evaluation.eval_id, "approved"), 403, "gate_denied");
  assert.deepEqual(originals(await api.evaluation(evaluation.eval_id)), before);
  setPrincipal("sam");
  evaluation = await api.overrideCheck(evaluation.eval_id, "C-04", "flag", "Verified purchase contract.");
  assert.equal(check(evaluation, "C-04").override.role, "supervisor");
  assert.equal((await api.decide(evaluation.eval_id, "approved")).transaction_status, "passed");
  const denials = (await api.audit("TXN-0005")).events.filter((event) => event.event === "decision.denied");
  assert.deepEqual(denials.map((event) => event.detail.action), ["override", "decision"]);
  console.log("d PASS: Ana override and approval denied; Sam succeeds; denied audits identify both actions");

  // e: A missing reason makes no write; denied chat leaves the evaluation intact.
  rows = await fresh();
  evaluation = await api.evaluation(row(rows, "TXN-0003").eval_id);
  const beforeNoReason = structuredClone(evaluation);
  const count = (await api.audit()).events.length;
  const missing = await api.ask(evaluation.eval_id, "switch C-04 to pass");
  assert.equal(missing.override.status, "needs_reason");
  assert.equal(missing.evaluation, undefined);
  assert.deepEqual(await api.evaluation(evaluation.eval_id), beforeNoReason);
  assert.equal((await api.audit()).events.length, count);
  const applied = await api.ask(evaluation.eval_id, "switch C-04 to pass because payroll customers spike at month-end");
  assert.equal(applied.override.status, "applied");
  assert.equal(applied.evaluation.effective_recommendation, "pass");
  assert.equal(check(applied.evaluation, "C-04").override.via, "chat");
  assert((await api.audit("TXN-0003")).events.some((event) => event.event === "check.overridden" && event.actor.id === "ana" && event.detail.via === "chat"));
  const high = await api.evaluation(row(rows, "TXN-0005").eval_id);
  const denied = await api.ask(high.eval_id, "switch C-04 to no-pass because supporting documents need review");
  assert.equal(denied.override.status, "denied");
  assert.equal(denied.evaluation, undefined);
  assert.deepEqual(await api.evaluation(high.eval_id), high);
  console.log("e PASS: reasoned chat override applied; no-reason request writes nothing; denied chat leaves evaluation unchanged");

  // f: Revert restores the original result and blocks approval again.
  evaluation = await api.overrideCheck(evaluation.eval_id, "C-04", null);
  assert.equal(check(evaluation, "C-04").override, null);
  assert.equal(check(evaluation, "C-04").effective_result, check(evaluation, "C-04").result);
  assert.equal(evaluation.effective_recommendation, "no_pass");
  await blocked(api.decide(evaluation.eval_id, "approved"), 409, "checks_not_cleared");
  assert((await api.audit("TXN-0003")).events.some((event) => event.event === "check.override_reverted" && event.actor.id === "ana"));
  assert.equal((await api.verifyChain()).ok, true);
  await tamperFixtureAudit();
  assert.equal((await api.verifyChain()).broken_at_seq, 1);
  console.log("f PASS: revert restores original and blocks approval; human audit event; chain integrity and tamper detection verified");

  // Hard-only decisions never create adjustments, and auditors cannot write.
  rows = await fresh();
  evaluation = await api.overrideCheck(row(rows, "TXN-0001").eval_id, "C-01", "flag", "Manual sanctions review completed.");
  const hardOnly = await api.decide(evaluation.eval_id, "approved");
  assert(hardOnly.memory_created.every((item) => item.kind === "precedent"));
  setPrincipal("aud");
  const untouched = await api.evaluation(row(rows, "TXN-0003").eval_id);
  await blocked(api.overrideCheck(untouched.eval_id, "C-04", "pass", "Reviewer context."), 403, "gate_denied");
  await blocked(api.decide(untouched.eval_id, "rejected"), 403, "gate_denied");
  assert.deepEqual(await api.evaluation(untouched.eval_id), untouched);
  console.log("Additional PASS: hard-only override creates no adjustment; auditor cannot override or decide");

  // Stub fetch: exercise endpoint switching without making a real request.
  apiSources.overrideCheck = "backend";
  let captured;
  globalThis.fetch = async (path, options) => {
    captured = { path, options };
    return { ok: true, json: async () => ({}) };
  };
  setPrincipal("sam");
  await api.overrideCheck("EVAL-test", "W-01", "pass", "Verified documentation.");
  assert.equal(captured.path, "/api/evaluations/EVAL-test/checks/W-01/override");
  assert.equal(captured.options.headers["X-Principal-Id"], "sam");
  assert.deepEqual(JSON.parse(captured.options.body), { result: "pass", reason: "Verified documentation." });
  await api.overrideCheck("EVAL-test", "W-01", null);
  assert.deepEqual(JSON.parse(captured.options.body), { result: null });
  console.log("API PASS: independent override endpoint switch, principal header, reason body and null revert body verified");
} finally {
  rmSync(compiled, { recursive: true, force: true });
}
