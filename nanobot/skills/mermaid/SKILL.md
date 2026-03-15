# Mermaid Diagrams Skill

Generate diagrams from text using [Mermaid](https://mermaid.js.org/).

## Requirements

- `@mermaid-js/mermaid-cli` (`npm install -g @mermaid-js/mermaid-cli`)

## Usage

1. Write Mermaid syntax to a `.mmd` file
2. Run `mmdc` to render SVG (only SVG format is supported)
3. Save the SVG to Media-Folder (~/.nanobot/media)
4. Display the SVG to user via `image` tool's display mode

### Basic Command

```bash
mmdc -i input.mmd -o output.svg -t default -b transparent
```

### Output Rules

- **Format**: Only generate SVG files (no PNG or PDF)
- **Location**: Save to Media-Folder: `/Users/tongmeng/.nanobot/media/`
- **Display**: Always use `image` tool with mode `display` to show the generated SVG

### File Naming

Use timestamp-based naming to avoid conflicts:
```
mermaid-<diagram-type>-<timestamp>.svg
```

Example: `mermaid-flowchart-202603151740.svg`

### Options

| Flag | Description |
|---|---|
| `-i` | Input `.mmd` file |
| `-o` | Output file (`.svg` only) |
| `-t` | Theme: `default`, `dark`, `forest`, `neutral` |
| `-b` | Background color (`transparent`, hex) |
| `-w` | Width in pixels (default: 800) |
| `-H` | Height in pixels |
| `-s` | Scale factor (default: 1, use 2-3 for high-res) |
| `-c` | Config JSON file for advanced theming |

### Supported Diagram Types

- **Flowchart**: `graph TD` / `graph LR`
- **Sequence**: `sequenceDiagram`
- **Class**: `classDiagram`
- **State**: `stateDiagram-v2`
- **ER**: `erDiagram`
- **Gantt**: `gantt`
- **Pie**: `pie`
- **Mindmap**: `mindmap`
- **Timeline**: `timeline`
- **Git graph**: `gitGraph`
- **Quadrant**: `quadrantChart`
- **Block**: `block-beta`

### Workflow

1. Determine the best diagram type for what the user wants
2. Write the `.mmd` file to `/tmp/mermaid-<name>.mmd`
3. Generate timestamp-based filename: `mermaid-<diagram-type>-<timestamp>.svg`
4. Render SVG: `mmdc -i /tmp/mermaid-<name>.mmd -o ~/.nanobot/media/mermaid-<name>-<timestamp>.svg -t default -b transparent`
5. Display the SVG to user: `image` tool with mode `display` and the generated SVG path
6. Clean up temp `.mmd` files if not needed

### Example Usage Flow

```
User: "创建一个用户登录流程图"
Agent:
  1. 创建 mermaid 语法 -> /tmp/mermaid-login.mmd
  2. 生成 SVG -> ~/.nanobot/media/mermaid-flowchart-202603151740.svg
  3. 调用 image 工具 display 模式展示给用户
```

### Example: Architecture Diagram

```mermaid
graph TD
    A[Client] -->|HTTPS| B[API Gateway]
    B --> C[Auth Service]
    B --> D[App Server]
    D --> E[(PostgreSQL)]
    D --> F[(Redis Cache)]
```

### Example: Sequence Diagram

```mermaid
sequenceDiagram
    participant U as User
    participant A as API
    participant DB as Database
    U->>A: POST /login
    A->>DB: Validate credentials
    DB-->>A: User record
    A-->>U: JWT token
```

### Tips

- Use `graph LR` for left-to-right flow, `graph TD` for top-down
- Keep node labels short — detail goes in tooltips or notes
- Use subgraphs to group related components
- For dark backgrounds, use `-t dark -b transparent`
- Scale `-s 2` or `-s 3` for sharp images on retina displays
- **Always use `pty: false`** when calling `mmdc`

### Theming

For custom colors, create a config JSON:

```json
{
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#f59e0b",
    "primaryTextColor": "#1a1a1a",
    "primaryBorderColor": "#d97706",
    "lineColor": "#6b7280",
    "secondaryColor": "#10b981",
    "tertiaryColor": "#3b82f6"
  }
}
```

Then: `mmdc -i input.mmd -o output.svg -c config.json`
