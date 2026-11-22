import { setTimeout as sleep } from 'node:timers/promises';

const [origin, deploymentSha, repositoryId, baselinePr, concurrentPrs, query,
  sourceLines, availabilityMinutes, maxSlowdown] = process.argv.slice(2);
const cookie = process.env.LIVINGDOCS_BENCHMARK_COOKIE;
const prs = (concurrentPrs ?? '').split(',');
const positiveInteger = (value) => /^[1-9]\d*$/.test(value ?? '');
const commitSha = (value) => /^[a-f0-9]{40}$/i.test(value ?? '');

if (!origin || !commitSha(deploymentSha) ||
    !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(repositoryId ?? '') ||
    !positiveInteger(baselinePr) || prs.length !== 20 || !prs.every(positiveInteger) ||
    new Set([baselinePr, ...prs]).size !== 21 || !query?.trim() ||
    Number(sourceLines) !== 100_000 || !positiveInteger(availabilityMinutes) ||
    !Number.isFinite(Number(maxSlowdown)) || Number(maxSlowdown) < 1 || !cookie) {
  console.error('Usage: node scripts/benchmark-acceptance.mjs TEST_ORIGIN DEPLOYED_SHA REPOSITORY_UUID BASELINE_PR 20_COMMA_SEPARATED_PRS SEARCH_QUERY 100000 AVAILABILITY_MINUTES MAX_SLOWDOWN');
  console.error('Set LIVINGDOCS_BENCHMARK_COOKIE in the test runner secret environment.');
  process.exit(2);
}

const server = new URL(origin);
if (!['https:', 'http:'].includes(server.protocol) || server.username || server.password ||
    server.href !== server.origin + '/' ||
    (server.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(server.hostname))) {
  throw new Error('Use an HTTPS origin or loopback HTTP origin for the isolated deployment.');
}

const repository = '/api/repositories/' + repositoryId;
const intervalMs = 10_000;
const timeoutMs = 125_000;

async function measure(path, expectedStatus, validate, options = {}, timeout = timeoutMs) {
  const started = performance.now();
  try {
    const response = await fetch(new URL(path, server), {
      ...options,
      redirect: 'error',
      signal: AbortSignal.timeout(timeout),
    });
    const body = await response.json();
    const evidence = response.status === expectedStatus ? validate(body) : null;
    return { ms: performance.now() - started, status: response.status, evidence };
  } catch {
    return { ms: performance.now() - started, status: null, evidence: null };
  }
}

const authorization = { Cookie: cookie };
const csrf = await measure('/api/auth/csrf', 200, (body) =>
  typeof body.token === 'string' && body.token.length > 0 ? body.token : null,
  { headers: authorization }, 5_000);
if (!csrf.evidence) throw new Error('Could not obtain a CSRF token from the test deployment.');
const writeHeaders = {
  Cookie: cookie.replace(/(?:^|;\s*)XSRF-TOKEN=[^;]*/g, '').replace(/^;\s*/, '') +
    '; XSRF-TOKEN=' + encodeURIComponent(csrf.evidence),
  'X-XSRF-TOKEN': csrf.evidence,
  'Content-Type': 'application/json',
};

async function analyze(pr) {
  const result = await measure(repository + '/drift/analyze', 201, (body) =>
    body.id && body.pull_request?.number === Number(pr) &&
    commitSha(body.pull_request.head_sha) && Array.isArray(body.findings)
      ? { reportId: body.id, headSha: body.pull_request.head_sha, warnings: body.warnings?.length ?? 0 }
      : null,
  { method: 'POST', headers: writeHeaders, body: JSON.stringify({ pullRequestNumber: Number(pr) }) });
  return { pr: Number(pr), ...result };
}

async function availability() {
  const durationMs = Number(availabilityMinutes) * 60_000;
  const started = performance.now();
  const probes = [];
  for (let offset = 0; offset < durationMs; offset += intervalMs) {
    await sleep(Math.max(0, started + offset - performance.now()));
    const probe = await measure('/actuator/health', 200, (body) =>
      body.status === 'UP' ? true : null, {}, 5_000);
    probes.push(probe);
  }
  await sleep(Math.max(0, started + durationMs - performance.now()));
  const percent = 100 * probes.filter((probe) => probe.evidence).length / probes.length;
  return { pass: percent >= 99.5, percent, intervalMs, durationMs, probes };
}

const startedAt = new Date().toISOString();
const uptime = availability();
const baseline = await analyze(baselinePr);
const concurrent = await Promise.all(prs.map(analyze));
const api = await measure(repository, 200, (body) => body.id === repositoryId ? true : null,
  { headers: authorization }, 5_000);
const search = await measure(repository + '/documentation/search?q=' + encodeURIComponent(query),
  200, (body) => Array.isArray(body.results) && body.results.length > 0 ? body.results.length : null,
  { headers: authorization }, 5_000);

const reports = [baseline, ...concurrent];
const distinctReports = new Set(reports.map((run) => run.evidence?.reportId)).size === reports.length;
const maxConcurrentMs = Math.max(...concurrent.map((run) => run.ms));
const checks = {
  drift: { pass: Boolean(baseline.evidence) && baseline.ms <= 120_000, baseline },
  concurrent: {
    pass: Boolean(baseline.evidence) && distinctReports &&
      concurrent.every((run) => run.evidence) &&
      maxConcurrentMs <= Math.min(120_000, baseline.ms * Number(maxSlowdown)),
    maxSlowdown: Number(maxSlowdown), maxConcurrentMs, runs: concurrent,
  },
  api: { pass: Boolean(api.evidence) && api.ms <= 2_000, ...api },
  search: { pass: Boolean(search.evidence) && search.ms <= 1_000, ...search },
  availability: await uptime,
};
const pass = Object.values(checks).every((check) => check.pass);
console.log(JSON.stringify({
  pass, deploymentSha, repositoryId, sourceLines: Number(sourceLines), startedAt,
  completedAt: new Date().toISOString(), checks,
}, null, 2));
process.exitCode = pass ? 0 : 1;
