# Recover remaining large source files

The following modules may still be landing as individual commits.
Meanwhile you can unpack this emergency bundle:

```bash
base64 -d REMAINING_SOURCES.b64 > remaining.tar.gz
tar xzf remaining.tar.gz
```

Files inside:
- src/core/storage.py
- src/epub/generator.py
- src/glossary/builder.py
- src/main.py
- src/parsers/epub_parser.py
- src/queue/batch_queue.py
- src/translation/engine.py
- src/ui/app.py
