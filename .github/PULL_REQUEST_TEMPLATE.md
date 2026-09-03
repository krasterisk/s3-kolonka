## Summary

<!-- Why this change exists. -->

## Test plan

- [ ] Gateway tests (`PYTHONPATH=. python -m unittest discover -s tests -v`)
- [ ] Firmware builds (`idf.py build`) if C/Kconfig changed
- [ ] Hardware check if UI, audio, or WebSocket behavior changed

## Checklist

- [ ] No secrets, production hosts, or `config.yaml`
- [ ] Docs / `docs/protocol.md` updated when the wire format changes
