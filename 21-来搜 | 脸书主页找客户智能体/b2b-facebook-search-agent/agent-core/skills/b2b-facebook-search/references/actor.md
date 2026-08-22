# Actor Reference

- Actor: `apify/facebook-search-scraper`
- mcpc session: `@apify`
- Required input: `categories`, `locations`, `resultsLimit`.
- Smoke-test cost control: set `resultsLimit=1`.

Use `fetch-actor-details` if an input fails:

```bash
mcpc --json @apify tools-call fetch-actor-details \
  '{"actor":"apify/facebook-search-scraper","output":{"inputSchema":true,"pricing":true}}'
```
