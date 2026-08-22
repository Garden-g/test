# Actor Reference

- Actor: `compass/crawler-google-places`
- mcpc session: `@apify`
- Required input: usually `searchStringsArray` plus a location field.
- Smoke-test cost control: set `maxCrawledPlacesPerSearch=1`, keep add-ons disabled.

Use `fetch-actor-details` if an input fails:

```bash
mcpc --json @apify tools-call fetch-actor-details \
  '{"actor":"compass/crawler-google-places","output":{"inputSchema":true,"pricing":true}}'
```
