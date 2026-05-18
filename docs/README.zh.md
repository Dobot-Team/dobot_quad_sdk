# Dobot Quad SDK 文档

本目录包含 Dobot Quad SDK 的官方文档，使用 MkDocs + Material 主题构建，支持中英文双语。

---

## 本地预览

直接打开dobot_quad_sdk\docs\site\index.html查看

## 本地预览（自行构建）

如果需要自行构建静态网站，则按以下步骤执行：

### 安装依赖

```bash
$ pip install -r requirements.docs.txt
```

### 启动本地服务器

```bash
$ mkdocs serve
```

访问 http://127.0.0.1:8000 预览文档。

### 构建静态文件

```bash
$ python build_local.py
```

构建结果位于 `site/` 目录。

---

## 参考资料

- [MkDocs 官方文档](https://www.mkdocs.org/)
