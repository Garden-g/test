# Actor Reference

- Actor: `apify/google-search-scraper`
- mcpc session: `@apify`
- Required input: `queries`
- Cost driver: pages scraped; use `maxPagesPerQuery=1` for smoke tests.

Useful fields commonly returned:

- `title`
- `url`
- `displayedUrl`
- `description`
- `searchQuery`
- `position`

Use `fetch-actor-details` if the Actor rejects an input:

```bash
mcpc --json @apify tools-call fetch-actor-details \
  '{"actor":"apify/google-search-scraper","output":{"inputSchema":true,"pricing":true}}'
```
