#!/usr/bin/env node
/**
 * Run an Apify Actor through mcpc and export its dataset.
 *
 * This avoids APIFY_TOKEN entirely. It uses the logged-in mcpc Apify session
 * and then writes the Actor dataset to CSV or JSON for the user.
 */

import { parseArgs } from 'node:util';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

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
        console.log('Usage: node scripts/run_mcp_actor.js --actor ACTOR --input JSON --output out.csv');
        process.exit(0);
    }
    if (!values.actor) throw new Error('Missing required argument: --actor');
    if (!values.input && !values['input-file']) throw new Error('Provide --input JSON or --input-file');
    const rawInput = values['input-file'] ? readFileSync(values['input-file'], 'utf-8') : values.input;
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

function callMcpcTool(session, toolName, payload) {
    const result = spawnSync('mcpc', ['--json', session, 'tools-call', toolName, JSON.stringify(payload)], {
        encoding: 'utf-8',
        maxBuffer: 1024 * 1024 * 50,
    });
    if (result.status !== 0) {
        if (result.error?.code === 'ENOENT') throw new Error('mcpc is not installed; ask before installing it globally.');
        throw new Error(`mcpc ${toolName} failed: ${result.stderr || result.stdout}`);
    }
    return JSON.parse(result.stdout);
}

function unwrapToolResult(raw) {
    if (raw?.isError) throw new Error(raw.content?.map((item) => item.text).join('\n') || JSON.stringify(raw));
    if (raw?.structuredContent && typeof raw.structuredContent === 'object') return raw.structuredContent;
    if (Array.isArray(raw?.content)) {
        for (const item of raw.content) {
            if (item.type === 'text' && typeof item.text === 'string') {
                try { return JSON.parse(item.text); } catch {}
            }
        }
    }
    return raw;
}

function findDeep(value, key) {
    if (!value || typeof value !== 'object') return undefined;
    if (Object.prototype.hasOwnProperty.call(value, key)) return value[key];
    for (const child of (Array.isArray(value) ? value : Object.values(value))) {
        const found = findDeep(child, key);
        if (found !== undefined) return found;
    }
    return undefined;
}

function csvCell(value) {
    if (value === null || value === undefined) return '';
    let text = typeof value === 'object' ? JSON.stringify(value) : String(value);
    if (text.length > 500) text = `${text.slice(0, 497)}...`;
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function toCsv(rows) {
    if (!rows.length) return '';
    const headers = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    return [headers.join(','), ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(','))].join('\n');
}

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
    if (!datasetId) throw new Error(`Actor run did not return a datasetId. Run ID: ${runId || 'unknown'}`);
    const outputResult = unwrapToolResult(callMcpcTool(args.session, 'get-actor-output', { datasetId, limit: args.limit }));
    const items = Array.isArray(outputResult.items) ? outputResult.items : [];
    const actorError = items.find((item) => item && typeof item.error === 'string');
    if (actorError) throw new Error(`Actor returned an error dataset item: ${actorError.error}`);
    if (args.jsonOutput) writeFileSync(args.jsonOutput, JSON.stringify(items, null, 2));
    if (args.output) writeFileSync(args.output, args.format === 'json' ? JSON.stringify(items, null, 2) : toCsv(items));
    console.log(JSON.stringify({ actor: args.actor, runId, datasetId, records: items.length, output: args.output || '', jsonOutput: args.jsonOutput || '' }, null, 2));
}

main().catch((error) => {
    console.error(error.message);
    process.exit(1);
});
