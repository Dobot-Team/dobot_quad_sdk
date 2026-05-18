# Dobot Quad SDK Documentation

This directory contains the official documentation for the Dobot Quad SDK, built with MkDocs + Material theme, supporting both Chinese and English.

---

## Local Preview

Open `dobot_quad_sdk\docs\site\index.html` directly in your browser.

## Local Preview (Build from Source)

If you need to build the static site yourself, follow these steps:

### Install Dependencies

```bash
$ pip install -r requirements.docs.txt
```

### Start Local Server

```bash
$ mkdocs serve
```

Visit http://127.0.0.1:8000 to preview the documentation.

### Build Static Files

```bash
$ python build_local.py
```

The build output is located in the `site/` directory.

---

## References

- [MkDocs Documentation](https://www.mkdocs.org/)
