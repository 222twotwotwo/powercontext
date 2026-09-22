/*
 * Copyright (c) 2026 OceanBase.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
// Evaluation-only JSONL bridge to the real CodeGraph library. No MCP server.
const readline = require('node:readline');
const path = require('node:path');
const fs = require('node:fs');
console.log = (...args) => process.stderr.write(args.join(' ') + '\n');
const { CodeGraph } = require(path.resolve(process.argv[2], 'dist/index.js'));
const { loadGrammarsForLanguages, isGrammarLoaded } = require(path.resolve(process.argv[2], 'dist/extraction/index.js'));
let graph;
let repositoryRoot;
const wire = (value) => JSON.stringify(value, (_key, item) => item instanceof Map ? [...item.values()] : item);
async function execute(request) {
  if (request.action === 'index') {
    if (graph) graph.close();
    const cache = path.join(request.root, '.codegraph');
    if (fs.existsSync(cache)) fs.rmSync(cache, { recursive: true });
    graph = await CodeGraph.init(request.root);
    repositoryRoot = request.root;
    await loadGrammarsForLanguages(['python']);
    if (!isGrammarLoaded('python')) throw new Error('Python grammar did not load');
    const indexed = await graph.indexFiles(request.files.map((file) => path.join(request.root, file)));
    if (!indexed.success) throw new Error(wire(indexed));
    graph.reinitializeResolver();
    const resolved = await graph.resolveReferencesBatched();
    return { indexed, resolved, stats: graph.getStats(), max_rss_kib: process.resourceUsage().maxRSS };
  }
  const op = request.operation;
  const limit = Math.min(op.limit || 20, 50);
  switch (op.kind) {
    case 'symbols':
      return graph.searchNodes(op.query, {
        languages: ['python'], limit,
        includePatterns: op.path_prefix ? [path.join(repositoryRoot, op.path_prefix), path.join(repositoryRoot, op.path_prefix, '**')] : undefined,
      });
    case 'explore':
      return graph.findRelevantContext(op.query, { searchLimit: 4, traversalDepth: 1, maxNodes: Math.min(limit, 16) });
    case 'callers': return graph.getCallers(op.symbol_id, op.depth || 1);
    case 'callees': return graph.getCallees(op.symbol_id, op.depth || 1);
    case 'impact': return graph.getImpactRadius(op.symbol_id, op.depth || 3);
    default: throw new Error('unsupported_capability');
  }
}
(async () => {
  for await (const line of readline.createInterface({ input: process.stdin })) {
    try {
      const request = JSON.parse(line);
      const result = await execute(request);
      process.stdout.write(wire({ result }) + '\n');
    } catch (error) {
      process.stdout.write(wire({ error: String(error.message || error) }) + '\n');
    }
  }
  if (graph) graph.close();
})().catch((error) => { process.stderr.write(String(error)); process.exitCode = 1; });
