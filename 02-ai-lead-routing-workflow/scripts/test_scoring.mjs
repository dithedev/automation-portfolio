#!/usr/bin/env node

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const workflow = JSON.parse(readFileSync(join(root, 'workflows', 'lead-routing-main.json'), 'utf8'));
const node = workflow.nodes.find((item) => item.name === 'Calculate Explainable Score');
assert(node, 'Scoring node not found');

const runNode = new Function('$', '$json', `return (async () => { ${node.parameters.jsCode} })();`);

const lead = {
  request_id: 'test-execution',
  received_at: '2026-09-08T00:00:00.000Z',
  idempotency_key: 'test-key-001',
  name: 'Test Lead',
  first_name: 'Test',
  last_name: 'Lead',
  email: 'test@example.com',
  email_masked: 'te***@example.com',
  company: 'Example Company',
  phone: '',
  message: 'We have a sufficiently detailed project enquiry that contains more than eighty characters for scoring.',
  estimated_budget: 0,
  source: 'test',
  consent_to_contact: true,
};

async function score(extraction, leadOverrides = {}) {
  const currentLead = { ...lead, ...leadOverrides };
  const select = (name) => {
    assert.equal(name, 'Normalize Lead Input');
    return { item: { json: currentLead } };
  };
  const result = await runNode(select, extraction === null ? { error: { message: 'mock error' } } : { output: extraction });
  return result[0].json;
}

const hot = await score({
  intent: 'new_project', requested_service: 'workflow_automation', urgency: 'immediate',
  budget_category: '20k_plus', decision_maker_signal: 'strong', summary: 'Hot test lead.',
  missing_information: [], confidence: 0.95,
});
assert.equal(hot.tier, 'hot');
assert.equal(hot.score, 100);

const warm = await score({
  intent: 'consultation', requested_service: 'crm_integration', urgency: 'this_quarter',
  budget_category: '5k_10k', decision_maker_signal: 'medium', summary: 'Warm test lead.',
  missing_information: [], confidence: 0.9,
});
assert.equal(warm.tier, 'warm');
assert.equal(warm.score, 61);

const cold = await score({
  intent: 'consultation', requested_service: 'other', urgency: 'exploring',
  budget_category: 'unknown', decision_maker_signal: 'unknown', summary: 'Cold test lead.',
  missing_information: ['budget'], confidence: 0.9,
}, { company: '', message: 'A short but valid generic enquiry.' });
assert.equal(cold.tier, 'cold');
assert.equal(cold.score, 2);

const coldCoreService = await score({
  intent: 'consultation', requested_service: 'workflow_automation', urgency: 'exploring',
  budget_category: 'unknown', decision_maker_signal: 'unknown', summary: 'Exploratory workflow automation enquiry.',
  missing_information: ['company', 'budget', 'timeline'], confidence: 0.9,
}, {
  company: '',
  message: 'The business goal is to copy website enquiries into Google Sheets automatically, with no approved budget or committed timeline.',
});
assert.equal(coldCoreService.tier, 'cold');
assert.equal(coldCoreService.score, 22);

const review = await score({
  intent: 'other', requested_service: 'unclear', urgency: 'unclear',
  budget_category: 'unknown', decision_maker_signal: 'unknown', summary: 'Unclear test lead.',
  missing_information: ['requested_service', 'timeline'], confidence: 0.4,
});
assert.equal(review.tier, 'needs_review');
assert(review.review_reasons.includes('low_confidence'));

const failed = await score(null);
assert.equal(failed.tier, 'needs_review');
assert(failed.review_reasons.includes('ai_extraction_failed'));

const explicitBudget = await score({
  intent: 'new_project', requested_service: 'ai_integration', urgency: 'within_month',
  budget_category: 'unknown', decision_maker_signal: 'medium', summary: 'Explicit budget test.',
  missing_information: [], confidence: 0.9,
}, { estimated_budget: 25000 });
assert.equal(explicitBudget.budget_category, '20k_plus');
assert.equal(explicitBudget.score_breakdown.budget, 30);

console.log('All embedded scoring tests passed.');
