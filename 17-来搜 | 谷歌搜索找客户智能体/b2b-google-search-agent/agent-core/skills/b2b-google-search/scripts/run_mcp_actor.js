#!/usr/bin/env node
/**
 * Run an Apify Actor through mcpc and export its dataset.
 *
 * Why this script exists:
 * - The skill should not require APIFY_TOKEN in a local .env file.
 * - mcpc already stores the user's Apify OAuth login profile.
 * - This script gives Codex a stable command for running Actors and saving CSV/JSON.
 */

import { parseArgs } from 'node:util';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

/**
 * Parse CLI arguments and normalize defaults.
 *
 * @returns {object} Validated command options.
 * @throws {Error} When required arguments are missing or malformed.
 */
function parseCliArguments() {
    const { values } = parseArgs({
        options: {
            actor: { type: 'string' },
            input: { type: 'string' },
            'input-file': { type: 'string' },
            output: { type: 'string' },
            'json-output': { type: 'string' },
            format: { type: 'string', default: 'csv' },
            session: { type: 'string', default: '@apify' },
            limit: { type: 'string', default: '1000' },
            timeout: { type: 'string', default: '600' },
            help: { type: 'boolean', short: 'h' },
        },
        allowPositionals: false,
    });

    if (values.help) {
        printHelp();
        process.exit(0);
    }

    if (!values.actor) {
        throw new Error('Missing required argument: --actor');
    }
    if (!values.input && !values['input-file']) {
        throw new Error('Provide --input JSON or --input-file');
    }

    const rawInput = values['input-file']
        ? readFileSync(values['input-file'], 'utf-8')
        : values.input;

    return {
        actor: values.actor,
        input: JSON.parse(rawInput),
        output: values.output,
        jsonOutput: values['json-output'],
        format: values.format || 'csv',
        session: values.session || '@apify',
        limit: Number.parseInt(values.limit, 10),
        timeout: Number.parseInt(values.timeout, 10),
    };
}

/**
 * Print CLI help for humans.
 *
 * @returns {void}
 */
function printHelp() {
    console.log(`
Run an Apify Actor through mcpc and export results.

Usage:
  node scripts/run_mcp_actor.js \\
    --actor "apify/google-search-scraper" \\
    --input '{"queries":"pet supplies importer USA","maxPagesPerQuery":1}' \\
    --output leads.csv \\
    --json-output leads.json
`);
}

/**
 * Call an mcpc tool and parse the JSON response.
 *
 * @param {string} session mcpc session name, usually @apify.
 * @param {string} toolName MCP tool name, for example call-actor.
 * @param {object} payload Tool arguments.
 * @returns {object} Parsed tool result.
 * @throws {Error} When mcpc exits non-zero or returns invalid JSON.
 */
function callMcpcTool(session, toolName, payload) {
    const result = spawnSync(
        'mcpc',
        ['--json', session, 'tools-call', toolName, JSON.stringify(payload)],
        {
            encoding: 'utf-8',
            maxBuffer: 1024 * 1024 * 50,
        }
    );

    if (result.status !== 0) {
        if (result.error?.code === 'ENOENT') {
            throw new Error('mcpc is not installed. Install it only after the user explicitly confirms the global npm change.');
        }
        throw new Error(`mcpc ${toolName} failed: ${result.stderr || result.stdout}`);
    }

    return JSON.parse(result.stdout);
}

/**
 * Convert common MCP tool-result shapes into a plain JavaScript object.
 *
 * @param {object} raw Raw mcpc JSON output.
 * @returns {object} Best-effort structured result.
 */
function unwrapToolResult(raw) {
    if (raw?.isError) {
        const text = raw.content?.map((item) => item.text).join('\n') || JSON.stringify(raw);
        throw new Error(text);
    }

    if (raw?.structuredContent && typeof raw.structuredContent === 'object') {
        return raw.structuredContent;
    }

    if (Array.isArray(raw?.content)) {
        for (const item of raw.content) {
            if (item.type === 'text' && typeof item.text === 'string') {
                try {
                    return JSON.parse(item.text);
                } catch {
                    continue;
                }
            }
        }
    }

    return raw;
}

/**
 * Recursively find the first value for a key in an object tree.
 *
 * @param {unknown} value Object, array, or primitive to inspect.
 * @param {string} key Key to find.
 * @returns {unknown} Matching value or undefined.
 */
function findDeep(value, key) {
    if (!value || typeof value !== 'object') {
        return undefined;
    }
    if (Object.prototype.hasOwnProperty.call(value, key)) {
        return value[key];
    }
    const children = Array.isArray(value) ? value : Object.values(value);
    for (const child of children) {
        const found = findDeep(child, key);
        if (found !== undefined) {
            return found;
        }
    }
    return undefined;
}

/**
 * Convert JSON records to a simple CSV string.
 *
 * @param {Array<object>} rows Dataset items.
 * @returns {string} CSV content.
 */
function toCsv(rows) {
    if (!rows.length) {
        return '';
    }

    const headers = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    const lines = [headers.join(',')];

    for (const row of rows) {
        lines.push(headers.map((header) => csvCell(row[header])).join(','));
    }

    return lines.join('\n');
}

/**
 * Escape one value for CSV.
 *
 * @param {unknown} value Raw cell value.
 * @returns {string} CSV-safe value.
 */
function csvCell(value) {
    if (value === null || value === undefined) {
        return '';
    }

    let text = typeof value === 'object' ? JSON.stringify(value) : String(value);
    if (text.length > 500) {
        text = `${text.slice(0, 497)}...`;
    }

    if (/[",\n\r]/.test(text)) {
        return `"${text.replace(/"/g, '""')}"`;
    }
    return text;
}

/**
 * Run the configured Actor and save results.
 *
 * @returns {Promise<void>}
 */
async function main() {
    const args = parseCliArguments();

    const runResult = unwrapToolResult(callMcpcTool(args.session, 'call-actor', {
        actor: args.actor,
        input: args.input,
        previewOutput: false,
        callOptions: { timeout: args.timeout },
    }));

    const runId = findDeep(runResult, 'runId');
    const datasetId = findDeep(runResult, 'datasetId');
    if (!datasetId) {
        throw new Error(`Actor run did not return a datasetId. Run ID: ${runId || 'unknown'}`);
    }

    const outputResult = unwrapToolResult(callMcpcTool(args.session, 'get-actor-output', {
        datasetId,
        limit: args.limit,
    }));

    const items = Array.isArray(outputResult.items) ? outputResult.items : [];
    const actorError = items.find((item) => item && typeof item.error === 'string');
    if (actorError) {
        throw new Error(`Actor returned an error dataset item: ${actorError.error}`);
    }

    if (args.jsonOutput) {
        writeFileSync(args.jsonOutput, JSON.stringify(items, null, 2));
    }
    if (args.output) {
        const content = args.format === 'json' ? JSON.stringify(items, null, 2) : toCsv(items);
        writeFileSync(args.output, content);
    }

    console.log(JSON.stringify({
        actor: args.actor,
        runId,
        datasetId,
        records: items.length,
        output: args.output || '',
        jsonOutput: args.jsonOutput || '',
    }, null, 2));
}

main().catch((error) => {
    console.error(error.message);
    process.exit(1);
});
