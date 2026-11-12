# Contributing

Thanks for helping improve the GeoShake Home Assistant integration.

## Development

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python pytest homeassistant aiomqtt
.venv/bin/python -m pytest tests/        # pure-core tests, no running Home Assistant needed
```

Architecture: a pure core (`const.py`: payload parsing, dedup, backoff; unit-tested) and a thin Home Assistant shell (`mqtt_client.py`, entities). Alarm semantics mirror the GeoShake cloud worker: a new event switches the sensor on, it clears 120 s after the last event, and `event_id` dedup absorbs QoS 1 redelivery.

## Brand images

Brand images live in `custom_components/geoshake/brand/`. Home Assistant 2026.3 and newer load them through the Brands Proxy API, so no `home-assistant/brands` pull request is needed. Older versions show a generic placeholder.

## README images

The images in `docs/images/` are generated from HTML sources kept in the GeoShake monorepo (`integrations/home-assistant/docs/images/src/`). Edit the source and render again instead of editing the images.

## Releasing

HACS and the Home Assistant Marketplace read the repository root: `hacs.json`, `README.md` and `custom_components/geoshake/`. The **Validate** (HACS action) and **Validate with hassfest** workflows run on every push; both must pass before a release. To release, bump `version` in `custom_components/geoshake/manifest.json`, then create a full GitHub release (not just a tag) with the tag `vX.Y.Z`.

## License

Apache License 2.0, see [LICENSE](LICENSE).
