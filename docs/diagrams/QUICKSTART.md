# Diagrama nuevo en 60 segundos

Sintaxis completa: [`SYNTAX.md`](SYNTAX.md). Flujo/troubleshooting completo:
[`README.md`](README.md).

1. Copiar un ejemplo como base:

   ```bash
   cp docs/diagrams/examples/mail-integration.eraser docs/diagrams/mi-diagrama.eraser
   ```

2. Editar `mi-diagrama.eraser`:

   ```
   title: Mi Diagrama
   direction: right

   Nodo A [icon: server]
   Nodo B [icon: postgresql]

   Nodo A > Nodo B: hace una query
   ```

3. Compilar y validar:

   ```bash
   .venv/bin/python docs/diagrams/eraser_to_archify.py \
       docs/diagrams/mi-diagrama.eraser \
       docs/diagrams/out/mi-diagrama.architecture.json \
       --validate
   ```

4. Si `--validate` no tira errores, renderizar:

   ```bash
   node ~/archify-pkg/archify/bin/archify.mjs render architecture \
       docs/diagrams/out/mi-diagrama.architecture.json \
       docs/diagrams/out/mi-diagrama.html
   ```

5. Abrir `docs/diagrams/out/mi-diagrama.html` en el navegador.

Si `--validate` se queja, ver la sección homónima en [`README.md`](README.md).
