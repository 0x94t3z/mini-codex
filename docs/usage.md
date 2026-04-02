# Usage

This page shows a few practical Mini Codex flows.

## Create Files

```text
Create a hello world script
```

Expected flow:

```text
You> Create a hello world script
Mini Codex> Writing hello.py...
Allow file write to hello.py? [y/N] y
Mini Codex> Created or updated `hello.py`.
```

## Work in a Folder

```bash
mini-codex --workdir ./examples
```

Then ask for changes inside `examples/`:

```text
Create a simple calculator script in calculator.py
```

## Read and Explain

```text
Read main.py and explain how tool approvals work
```

## Move Files

```text
Move hello.py to examples/hello.py
```

Mini Codex will usually create the target folder if it needs to.

## Check Version

```bash
mini-codex --version
```

## Use OpenAI

```bash
mini-codex --provider openai --model your-openai-model-id
```

Make sure `OPENAI_API_KEY` is set before you run it.

## Use Gemini

```bash
mini-codex --provider gemini --model gemini-2.5-flash
```

Make sure `GEMINI_API_KEY` is set before you run it.

## Use xAI

```bash
mini-codex --provider xai --model grok-4.20-beta-latest-non-reasoning
```

Make sure `XAI_API_KEY` is set before you run it.
