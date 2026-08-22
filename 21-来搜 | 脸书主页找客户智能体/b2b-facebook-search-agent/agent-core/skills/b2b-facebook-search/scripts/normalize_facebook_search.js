#!/usr/bin/env node
/**
 * Normalize raw Facebook Search Actor JSON into a B2B CSV.
 *
 * The Actor can return different field names across pages. This script keeps a
 * stable output surface so the user can filter leads without reading raw JSON.
 */

import { parseArgs } from 'node:util';
import { readFileSync, writeFileSync } from 'node:fs';

const OUTPUT_HEADERS = [
    'company_name',
    'website',
    'country',
    'city',
    'customer_type',
    'contact_name',
    'job_title',
    'email',
    'phone',
    'linkedin_url',
    'facebook_url',
    'instagram_url',
    'source_platform',
    'source_url',
    'notes',
    'page_category',
    'followers',
    'likes',
    'rating',
    'verified',
    'creation_date',
    'messenger_url',
];

/**
 * Parse CLI arguments.
 *
 * @returns {{inputJson: string, output: string, customerType: string}}
 */
function parseCliArguments() {
    const { values } = parseArgs({
        options: {
            'input-json': { type: 'string' },
            output: { type: 'string' },
            'customer-type': { type: 'string' },
            help: { type: 'boolean', short: 'h' },
        },
        allowPositionals: false,
    });

    if (values.help) {
        console.log('Usage: node normalize_facebook_search.js --input-json raw.json --output b2b.csv --customer-type wholesaler');
        process.exit(0);
    }
    if (!values['input-json']) throw new Error('Missing required argument: --input-json');
    if (!values.output) throw new Error('Missing required argument: --output');
    if (!values['customer-type']) throw new Error('Missing required argument: --customer-type');

    return {
        inputJson: values['input-json'],
        output: values.output,
        customerType: values['customer-type'],
    };
}

/**
 * Return a trimmed string for any primitive value.
 *
 * @param {unknown} value Raw value.
 * @returns {string}
 */
function asString(value) {
    if (value === null || value === undefined) return '';
    return String(value).trim();
}

/**
 * Pick the first meaningful field from a record.
 *
 * @param {Record<string, unknown>} record Raw actor item.
 * @param {string[]} keys Candidate keys.
 * @returns {string}
 */
function pick(record, keys) {
    for (const key of keys) {
        const value = asString(record[key]);
        if (value) return value;
    }
    return '';
}

/**
 * Recursively collect URLs from nested raw values.
 *
 * @param {unknown} value Raw nested value.
 * @param {Set<string>} urls Mutable collector.
 * @returns {Set<string>}
 */
function collectUrls(value, urls = new Set()) {
    if (typeof value === 'string') {
        for (const match of value.match(/https?:\/\/[^\s")]+/g) || []) {
            urls.add(match);
        }
        return urls;
    }
    if (Array.isArray(value)) {
        value.forEach((item) => collectUrls(item, urls));
        return urls;
    }
    if (value && typeof value === 'object') {
        Object.values(value).forEach((item) => collectUrls(item, urls));
    }
    return urls;
}

/**
 * Find the first URL containing one of the requested domain fragments.
 *
 * @param {Record<string, unknown>} record Raw actor item.
 * @param {string[]} fragments Domain fragments.
 * @returns {string}
 */
function findUrl(record, fragments) {
    return [...collectUrls(record)].find((url) => fragments.some((part) => url.toLowerCase().includes(part))) || '';
}

/**
 * Build a compact notes field from useful raw fragments.
 *
 * @param {Record<string, unknown>} record Raw actor item.
 * @returns {string}
 */
function buildNotes(record) {
    const parts = [
        pick(record, ['address']),
        pick(record, ['info', 'description']),
        pick(record, ['ad_status']),
    ].filter(Boolean);
    const text = parts.join(' | ');
    return text.length > 600 ? `${text.slice(0, 597)}...` : text;
}

/**
 * Normalize one raw Facebook page result.
 *
 * @param {Record<string, unknown>} record Raw actor item.
 * @param {string} customerType User-confirmed customer type.
 * @returns {Record<string, string>}
 */
function normalizeRecord(record, customerType) {
    const facebookUrl = pick(record, ['facebookUrl', 'pageUrl', 'url']) || findUrl(record, ['facebook.com']);
    const category = Array.isArray(record.categories) ? record.categories.map(asString).filter(Boolean).join(' | ') : asString(record.categories);

    return {
        company_name: pick(record, ['title', 'name', 'pageName', 'pageTitle']).split(' | ')[0].trim(),
        website: pick(record, ['website']),
        country: '',
        city: '',
        customer_type: customerType,
        contact_name: '',
        job_title: '',
        email: pick(record, ['email']),
        phone: pick(record, ['phone']),
        linkedin_url: findUrl(record, ['linkedin.com']),
        facebook_url: facebookUrl,
        instagram_url: findUrl(record, ['instagram.com']),
        source_platform: 'Facebook Search',
        source_url: facebookUrl,
        notes: buildNotes(record),
        page_category: category,
        followers: pick(record, ['followers']),
        likes: pick(record, ['likes']),
        rating: pick(record, ['ratingOverall', 'rating', 'ratingCount']),
        verified: pick(record, ['verified', 'isVerified', 'pageVerified']),
        creation_date: pick(record, ['creation_date']),
        messenger_url: pick(record, ['messenger']) || findUrl(record, ['m.me/', 'messenger.com']),
    };
}

/**
 * Escape one CSV cell.
 *
 * @param {unknown} value Raw cell value.
 * @returns {string}
 */
function csvCell(value) {
    const text = asString(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * Convert normalized rows into CSV.
 *
 * @param {Array<Record<string, string>>} rows Normalized rows.
 * @returns {string}
 */
function toCsv(rows) {
    const lines = [OUTPUT_HEADERS.join(',')];
    for (const row of rows) {
        lines.push(OUTPUT_HEADERS.map((header) => csvCell(row[header])).join(','));
    }
    return lines.join('\n');
}

function main() {
    const args = parseCliArguments();
    const raw = JSON.parse(readFileSync(args.inputJson, 'utf-8'));
    if (!Array.isArray(raw)) throw new Error('Raw JSON must be an array.');

    const seen = new Set();
    const rows = [];
    for (const item of raw) {
        const row = normalizeRecord(item, args.customerType);
        const key = (row.facebook_url || row.website || row.company_name).toLowerCase();
        if (!key || seen.has(key)) continue;
        seen.add(key);
        rows.push(row);
    }

    writeFileSync(args.output, toCsv(rows));
    console.log(JSON.stringify({ records: rows.length, output: args.output }, null, 2));
}

main();
