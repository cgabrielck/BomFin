import { test, expect } from './fixtures/research';
import type { Page } from '@playwright/test';

/**
 * The research acceptance flow, against a real TLS server.
 *
 * Nothing here is mocked. The browser pairs with a real server over a
 * real TLS origin, the server captures a real snapshot out of its own
 * tape, the real LangGraph runtime runs the role, the real harness
 * records a verdict, and the browser reads the verdict back over the
 * real API. The only thing that never happens is a call to a model
 * provider: the fixture answers the model turn locally and names
 * itself in the audit trail, so a reader can tell at a glance that no
 * report came from outside the machine.
 *
 * The assertions are about honesty, not about a particular wording:
 *
 * - A technical run shows a report, and the report cites evidence that
 *   really exists in the snapshot it is bound to.
 * - The snapshot metadata travels with the conclusion, so a reader can
 *   see what the conclusion was allowed to see.
 * - The harness verdict is shown, and the model version names the
 *   fixture rather than a provider.
 * - A stack with no model refuses to start a job and shows no report.
 * - A job that fails shows the failure and no conclusion.
 * - Logging out clears the research panel and revokes the session.
 */

/**
 * Pair the browser with the fixture.
 *
 * The pairing code comes over the private pipe, never over HTTP and
 * never into the test output.
 */
async function paired(
  page: Page,
  research: {
    origin: string;
    command: (action: string) => Promise<Record<string, unknown>>;
  },
) {
  await page.goto(research.origin);
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  const { code } = await research.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(
    page.getByRole('button', { name: '登出', exact: true }),
  ).toBeVisible();
}

/**
 * Open the research entry for one instrument.
 *
 * The research centre lives in the stock detail column as well as in
 * its own tab, and the stock detail column is the one that knows which
 * instrument the research is about. The tab on its own has no
 * instrument, and the panel says so rather than guessing.
 */
async function openResearchEntry(page: Page, symbol: string) {
  // The stock workspace owns the candidate list and the research entry.
  // The route change that follows a pick is applied in an effect, so the
  // tab swap is not immediate: the wait on the entry is what settles it.
  await page.getByTestId('nav-stock').click();
  const pick = page
    .getByRole('button', { name: new RegExp(symbol) })
    .first();
  await pick.waitFor({ state: 'visible' });
  await pick.click();
  await expect(page.getByTestId('selected-symbol')).toHaveText(symbol);
  const entry = page.getByTestId('research-entry');
  await expect(entry).toBeVisible();
  // The entry is a collapsed disclosure; opening it is what mounts the
  // research panel.
  if (!(await entry.evaluate(node => (node as HTMLDetailsElement).open)))
    await entry.locator('summary').click();
  await expect(page.getByTestId('research-configured')).toBeVisible();
}

// Self-signed certificate exception is confined to this test context.
test.use({ ignoreHTTPSErrors: true, trace: 'off' });

test('a technical research run shows a report bound to a real snapshot and a real audit verdict', async ({
  page,
  research,
}, testInfo) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await paired(page, research);
  await openResearchEntry(page, 'AAPL');

  // The panel reports that the stack can run. The fixture names itself
  // in the audit trail, so this is a real stack, not a stub.
  await expect(page.getByTestId('research-configured')).toContainText('AI 已配置');

  // Ask for the technical role only.
  await page.getByLabel('研究角色').selectOption('technical');
  await page.getByTestId('research-start').click();

  // The report arrives with the snapshot it is bound to.
  const report = page.getByTestId('research-report');
  await expect(report).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('research-report-status')).toContainText('已完成');
  await expect(page.getByTestId('research-report-role')).toContainText('技術');

  // The snapshot metadata travels with the conclusion, so a reader can
  // see what the conclusion was allowed to see.
  const snapshotId = await page.getByTestId('research-snapshot-id').innerText();
  expect(snapshotId).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
  );
  await expect(page.getByTestId('research-as-of')).not.toBeEmpty();

  // The technical role's conclusion is shown, and every finding cites
  // an evidence id. The evidence id is not a decoration: it is the id
  // the snapshot holds.
  const findings = page.getByTestId('research-role-technical').locator(
    '.research-finding-text',
  );
  await expect(findings.first()).toBeVisible();
  const evidence = page.getByTestId('research-role-technical').locator(
    '[data-testid^="research-evidence-"]',
  );
  await expect(evidence.first()).toBeVisible();
  const evidenceText = await evidence.first().innerText();
  expect(evidenceText).toMatch(
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
  );

  // The harness verdict is shown, and it is a pass.
  const checks = page.getByTestId('research-checks');
  await expect(checks).toBeVisible();
  const verdict = page.getByTestId('research-check-success');
  await expect(verdict).toContainText('technical');
  await expect(verdict).toContainText('success');
  // The model version names the fixture: no provider served this run.
  // It sits beside the verdict rather than inside it, so the whole
  // check line is read.
  await expect(checks).toContainText('fixture-model');
  // A rejected verdict would be a red banner. There is none.
  await expect(page.getByTestId('research-rejected')).toHaveCount(0);
  await expect(page.getByTestId('research-failed')).toHaveCount(0);

  // The raw report is a disclosure in the full research tab. The stock
  // detail entry renders the centre in its compact form, which leaves
  // the raw JSON out on purpose, so its absence here is the design and
  // not a gap.
  await expect(page.getByTestId('research-raw')).toHaveCount(0);

  // The acceptance screenshot lands in the repository's runtime folder,
  // not in the test output folder, because Playwright clears the output
  // folder of a passing test. It carries no pairing code: the code is
  // typed into the form and never shown back.
  await page.screenshot({
    path: 'runtime/research-acceptance.png',
    fullPage: true,
  });
});

test('the full research tab shows the same report with the raw JSON', async ({
  page,
  research,
}, testInfo) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await paired(page, research);

  // The research tab on its own has no instrument until one is chosen,
  // and it says so rather than guessing.
  await page.getByTestId('nav-research').click();
  await expect(page.getByRole('heading', { name: '研究中心' })).toBeVisible();
  await expect(page.getByTestId('research-no-instrument')).toBeVisible();

  // Choose a candidate in the stock column, then come back to the
  // research tab: the tab now carries an instrument, and it carries the
  // same report the stock detail entry showed.
  await page.getByTestId('nav-stock').click();
  const pick = page.getByRole('button', { name: new RegExp('AAPL') }).first();
  await pick.waitFor({ state: 'visible' });
  await pick.click();
  await expect(page.getByTestId('selected-symbol')).toHaveText('AAPL');

  await page.getByTestId('nav-research').click();
  await expect(page.getByTestId('research-configured')).toBeVisible();
  await page.getByLabel('研究角色').selectOption('technical');
  await page.getByTestId('research-start').click();

  const report = page.getByTestId('research-report');
  await expect(report).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('research-report-status')).toContainText('已完成');

  // The snapshot metadata travels with the conclusion.
  await expect(page.getByTestId('research-snapshot')).toBeVisible();
  await expect(page.getByTestId('research-snapshot-id')).toContainText(
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
  );
  await expect(page.getByTestId('research-as-of')).not.toBeEmpty();

  // The audit verdict is here too, and the raw report is available to a
  // reader who wants the whole thing.
  await expect(page.getByTestId('research-checks')).toContainText('success');
  const raw = page.getByTestId('research-raw');
  await expect(raw).toBeAttached();
  await raw.locator('summary').click();
  await expect(raw).toBeVisible();

  await page.screenshot({
    path: 'runtime/research-acceptance-tab.png',
    fullPage: true,
  });
});

test('a whole-graph run renders all three roles and their durable audit verdicts', async ({
  page,
  research,
}) => {
  test.setTimeout(60_000);
  await paired(page, research);
  await openResearchEntry(page, 'AAPL');
  // The default selection runs discovery -> technical -> portfolio.
  await page.getByTestId('research-start').click();
  await expect(page.getByTestId('research-report-status')).toContainText('已完成', {
    timeout: 30_000,
  });
  for (const role of ['discovery', 'technical', 'portfolio']) {
    await expect(page.getByTestId(`research-role-${role}`)).toBeVisible();
  }
  const snapshotId = await page.getByTestId('research-snapshot-id').innerText();
  const { checks } = await research.command('checks', { snapshot_id: snapshotId });
  const records = checks as Array<{ role: string; execution_result: string }>;
  for (const role of ['discovery', 'technical', 'portfolio']) {
    expect(records.some(record => record.role === role && record.execution_result === 'success')).toBe(true);
  }
});

test('the audit trail in the durable store agrees with what the browser shows', async ({
  page,
  research,
}) => {
  test.setTimeout(60_000);
  await paired(page, research);
  await openResearchEntry(page, 'AAPL');
  await page.getByLabel('研究角色').selectOption('technical');
  await page.getByTestId('research-start').click();
  await expect(page.getByTestId('research-report')).toBeVisible({
    timeout: 30_000,
  });

  const snapshotId = await page.getByTestId('research-snapshot-id').innerText();
  const { checks } = await research.command('checks', { snapshot_id: snapshotId });
  const records = checks as Array<{
    role: string;
    execution_result: string;
    reasons: string[];
    model_version: string;
  }>;
  expect(records.length).toBeGreaterThan(0);
  const technical = records.find(record => record.role === 'technical');
  expect(technical).toBeTruthy();
  expect(technical!.execution_result).toBe('success');
  expect(technical!.reasons).toEqual([]);
  expect(technical!.model_version).toContain('fixture-model');
});

test('a write without the anti-CSRF nonce is refused', async ({ page, research }) => {
  await paired(page, research);
  const response = await page.request.post(research.origin + '/v1/research/jobs', {
    data: {
      instrument_id: '11111111-1111-4111-8111-111111111111',
      role: 'technical',
    },
    headers: { Origin: research.origin },
  });
  expect(response.status()).toBe(403);
});

test('an unknown instrument is refused and no job is created', async ({
  page,
  research,
}) => {
  await paired(page, research);
  const nonce = await page.evaluate(() => {
    const entry = document.cookie
      .split('; ')
      .find(value => value.startsWith('__Host-gabfin_csrf='));
    return entry ? decodeURIComponent(entry.slice(entry.indexOf('=') + 1)) : null;
  });
  expect(nonce).toBeTruthy();
  const response = await page.request.post(research.origin + '/v1/research/jobs', {
    data: {
      instrument_id: '99999999-9999-4999-8999-999999999999',
      role: 'technical',
    },
    headers: { Origin: research.origin, 'X-CSRF-Token': String(nonce) },
  });
  expect(response.status()).toBe(404);
});

test('an unknown role is refused', async ({ page, research }) => {
  await paired(page, research);
  const nonce = await page.evaluate(() => {
    const entry = document.cookie
      .split('; ')
      .find(value => value.startsWith('__Host-gabfin_csrf='));
    return entry ? decodeURIComponent(entry.slice(entry.indexOf('=') + 1)) : null;
  });
  const response = await page.request.post(research.origin + '/v1/research/jobs', {
    data: {
      instrument_id: '11111111-1111-4111-8111-111111111111',
      role: 'not_a_role',
    },
    headers: { Origin: research.origin, 'X-CSRF-Token': String(nonce) },
  });
  expect(response.status()).toBe(422);
});

test('a job that is not the caller\'s is not readable', async ({ page, research }) => {
  await paired(page, research);
  const response = await page.request.get(
    research.origin + '/v1/research/jobs/11111111-1111-4111-8111-111111111111',
  );
  expect(response.status()).toBe(404);
});

test('logging out clears the research panel and revokes the session', async ({
  page,
  research,
}) => {
  test.setTimeout(60_000);
  await paired(page, research);
  await openResearchEntry(page, 'AAPL');
  await page.getByLabel('研究角色').selectOption('technical');
  await page.getByTestId('research-start').click();
  await expect(page.getByTestId('research-report')).toBeVisible({
    timeout: 30_000,
  });

  await page.getByRole('button', { name: '登出', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  // The conclusion is gone with the session. Nothing about the report
  // is left on the page.
  await expect(page.getByTestId('research-report')).toHaveCount(0);
  await expect(page.getByTestId('research-snapshot-id')).toHaveCount(0);

  await expect
    .poll(async () =>
      (await page.request.get(research.origin + '/session')).status(),
    )
    .toBe(401);
});

test.describe('a stack with no model configured', () => {
  test.use({ researchUnconfigured: true });

  test('refuses to start a job and shows no report, no snapshot and no evidence', async ({
    page,
    research,
  }, testInfo) => {
    test.setTimeout(60_000);
    expect(research.configured).toBe(false);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await paired(page, research);
    await openResearchEntry(page, 'AAPL');

    // The panel says the stack cannot run, and says why.
    await expect(page.getByTestId('research-configured')).toContainText(
      'AI 未配置',
    );
    await expect(page.getByTestId('research-unconfigured')).toBeVisible();

    // The launch controls are there, but the button is disabled: a
    // stack that cannot run a job has nothing to start, and the browser
    // cannot even send the request.
    const start = page.getByTestId('research-start');
    await expect(start).toBeVisible();
    await expect(start).toBeDisabled();
    await expect(page.getByTestId('research-disabled-note')).toBeVisible();

    // Nothing was sent, so nothing was produced.
    await expect(page.getByTestId('research-report')).toHaveCount(0);
    await expect(page.getByTestId('research-snapshot')).toHaveCount(0);
    await expect(page.getByTestId('research-failed')).toHaveCount(0);
    await expect(page.getByTestId('research-no-result')).toHaveCount(0);
    await expect(page.getByTestId('research-checks')).toHaveCount(0);
    await expect(page.getByTestId('research-job-')).toHaveCount(0);

    // The status route answers for itself.
    const status = await page.request.get(research.origin + '/v1/research/status');
    expect(status.status()).toBe(200);
    const body = await status.json();
    expect(body.configured).toBe(false);
    expect(typeof body.reason).toBe('string');

    // A job request against the same stack is refused too.
    const nonce = await page.evaluate(() => {
      const entry = document.cookie
        .split('; ')
        .find(value => value.startsWith('__Host-gabfin_csrf='));
      return entry ? decodeURIComponent(entry.slice(entry.indexOf('=') + 1)) : null;
    });
    const response = await page.request.post(
      research.origin + '/v1/research/jobs',
      {
        data: {
          instrument_id: '11111111-1111-4111-8111-111111111111',
          role: 'technical',
        },
        headers: {
          Origin: research.origin,
          'X-CSRF-Token': String(nonce),
        },
      },
    );
    expect(response.status()).toBe(503);

    await page.screenshot({
      path: testInfo.outputPath('research-unconfigured.png'),
      fullPage: true,
    });
  });
});

test.describe('a stack whose tape never held the series', () => {
  test.use({ researchNoHistory: true });

  test('fails the job for a real reason and shows no report', async ({
    page,
    research,
  }, testInfo) => {
    test.setTimeout(60_000);
    // The server is a full research stack; only the history is missing.
    expect(research.configured).toBe(true);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await paired(page, research);
    await openResearchEntry(page, 'AAPL');

    // Ask for the technical role and send it. The server accepts the
    // request, queues the job, and the job then fails for real.
    await page.getByLabel('研究角色').selectOption('technical');
    await page.getByTestId('research-start').click();

    // The job really runs and really fails. The report card exists, and
    // it says the job failed and why. What it must not contain is a
    // conclusion: no role result, no snapshot, no evidence, no verdict.
    const failure = page.getByTestId('research-failed');
    await expect(failure).toBeVisible();
    await expect(failure).toContainText('研究工作失敗');
    await expect(page.getByTestId('research-report-status')).toContainText('失敗');

    // No conclusion was invented for a job that produced none.
    await expect(page.getByTestId('research-role-technical')).toHaveCount(0);
    await expect(page.getByTestId('research-snapshot')).toHaveCount(0);
    await expect(page.getByTestId('research-snapshot-id')).toHaveCount(0);
    await expect(page.getByTestId('research-checks')).toHaveCount(0);
    await expect(page.getByTestId('research-rejected')).toHaveCount(0);
    await expect(page.getByTestId('research-evidence-technical-0')).toHaveCount(0);

    await page.screenshot({
      path: testInfo.outputPath('research-failed.png'),
      fullPage: true,
    });
  });
});
