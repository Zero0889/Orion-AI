/**
 * Mini-renderer de markdown para los mensajes del chat.
 *
 * Sin dependencias externas (cero packages añadidos al bundle). Cubre lo
 * que Gemini y los agentes secundarios emiten en >95% de los casos:
 *   - Headings  (# ## ###)
 *   - Bold      (**text**)
 *   - Italic    (*text*)
 *   - Inline    (`code`)
 *   - Block     (```lang\n...\n```)
 *   - Links     ([text](url)) con rel/target seguros
 *   - Listas    (- item / 1. item) con anidamiento básico
 *   - Quotes    (> text)
 *   - Hard line breaks
 *
 * NO soporta tablas, footnotes, HTML inline. Si en algún momento el output
 * de algún agente requiere alguno, vale la pena cambiar a `react-markdown`
 * + `remark-gfm`. Hasta entonces, esto mantiene el bundle pequeño.
 *
 * Seguridad: nunca emitimos `dangerouslySetInnerHTML`. Todo va por React,
 * por lo que el texto del LLM no puede inyectar HTML/JS en la página.
 */

import { Fragment, useMemo, useState } from "react";
import katex from "katex";

interface Props {
  /** Cuerpo markdown a renderizar. */
  source: string;
}

/* ─── Entry point ───────────────────────────────────────────────────── */
export function Markdown({ source }: Props) {
  // Normalizamos line endings de Windows.
  const text = source.replace(/\r\n?/g, "\n");
  const blocks = splitBlocks(text);
  return (
    <div className="markdown leading-[1.7] text-[15px] text-text space-y-3">
      {blocks.map((b, i) => (
        <Fragment key={i}>{renderBlock(b)}</Fragment>
      ))}
    </div>
  );
}

/* ─── Block-level parsing ───────────────────────────────────────────── */

type Block =
  | { kind: "code"; lang: string; body: string }
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "quote"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "hr" }
  | { kind: "math_display"; body: string }
  | { kind: "p"; text: string };

function splitBlocks(src: string): Block[] {
  const out: Block[] = [];
  const lines = src.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // fenced code block
    const fence = /^```([a-zA-Z0-9_+-]*)\s*$/.exec(line);
    if (fence) {
      const lang = fence[1] || "";
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) {
        body.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing ```
      out.push({ kind: "code", lang, body: body.join("\n") });
      continue;
    }

    // blank line → just skip
    if (/^\s*$/.test(line)) {
      i++;
      continue;
    }

    // heading
    const h = /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (h) {
      out.push({
        kind: "heading",
        level: h[1].length as 1 | 2 | 3,
        text: h[2],
      });
      i++;
      continue;
    }

    // hr: --- / *** / ___ (al menos 3 del mismo char, opcionalmente con espacios)
    if (/^\s*(?:-\s*){3,}$|^\s*(?:\*\s*){3,}$|^\s*(?:_\s*){3,}$/.test(line)) {
      out.push({ kind: "hr" });
      i++;
      continue;
    }

    // blockquote (multi-line)
    if (/^>\s?/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      out.push({ kind: "quote", text: buf.join(" ") });
      continue;
    }

    // ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      out.push({ kind: "ol", items });
      continue;
    }

    // unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
        i++;
      }
      out.push({ kind: "ul", items });
      continue;
    }

    // display math: $$ ... $$ or \[ ... \] (single or multi-line)
    if (/^\$\$/.test(line) || /^\\\[/.test(line)) {
      const isBracket = /^\\\[/.test(line);
      const closePat = isBracket ? /^\\\]\s*$/ : /^\$\$\s*$/;
      const singleRe = isBracket
        ? /^\\\[(.+?)\\\]\s*$/
        : /^\$\$(.+?)\$\$\s*$/;

      // single-line
      const single = singleRe.exec(line);
      if (single) {
        out.push({ kind: "math_display", body: single[1].trim() });
        i++;
        continue;
      }
      // multi-line
      const body: string[] = [];
      i++;
      while (i < lines.length && !closePat.test(lines[i])) {
        body.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing $$ or \]
      out.push({ kind: "math_display", body: body.join("\n").trim() });
      continue;
    }

    // paragraph: junta líneas hasta una en blanco o un bloque especial
    const para: string[] = [line];
    i++;
    while (
      i < lines.length &&
      !/^\s*$/.test(lines[i]) &&
      !/^```/.test(lines[i]) &&
      !/^\$\$/.test(lines[i]) &&
      !/^\\\[/.test(lines[i]) &&
      !/^#{1,3}\s/.test(lines[i]) &&
      !/^>/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push({ kind: "p", text: para.join("\n") });
  }
  return out;
}

function renderBlock(b: Block) {
  switch (b.kind) {
    case "heading": {
      const cls =
        b.level === 1 ? "text-xl font-semibold mt-2 mb-1 text-text"
        : b.level === 2 ? "text-lg font-semibold mt-2 mb-1 text-text"
        : "text-base font-semibold mt-1 text-text";
      const H = (`h${b.level}` as unknown) as "h1";
      return <H className={cls}><Inline text={b.text} /></H>;
    }
    case "hr":
      return <hr className="border-white/[0.08]" />;
    case "quote":
      return (
        <blockquote className="border-l-2 border-pri/40 pl-3 text-text-dim italic">
          <Inline text={b.text} />
        </blockquote>
      );
    case "ul":
      return (
        <ul className="list-disc list-outside pl-5 space-y-1">
          {b.items.map((it, j) => (
            <li key={j}><Inline text={it} /></li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol className="list-decimal list-outside pl-5 space-y-1">
          {b.items.map((it, j) => (
            <li key={j}><Inline text={it} /></li>
          ))}
        </ol>
      );
    case "math_display":
      return <KatexDisplay body={b.body} />;
    case "code":
      return <CodeBlock lang={b.lang} body={b.body} />;
    case "p":
      return (
        <p className="whitespace-pre-wrap"><Inline text={b.text} /></p>
      );
  }
}

/* ─── Inline parsing (bold/italic/code/links) ──────────────────────── */

type Inline =
  | { t: "text"; v: string }
  | { t: "bold"; v: Inline[] }
  | { t: "italic"; v: Inline[] }
  | { t: "code"; v: string }
  | { t: "math"; v: string }
  | { t: "link"; v: Inline[]; href: string };

function Inline({ text }: { text: string }) {
  return <>{renderInline(parseInline(text))}</>;
}

function renderInline(nodes: Inline[]): React.ReactNode {
  return nodes.map((n, i) => {
    switch (n.t) {
      case "text":   return <Fragment key={i}>{n.v}</Fragment>;
      case "bold":   return <strong key={i} className="font-semibold text-text">{renderInline(n.v)}</strong>;
      case "italic": return <em key={i} className="italic">{renderInline(n.v)}</em>;
      case "code":   return (
        <code key={i} className="px-1.5 py-0.5 rounded bg-white/[0.06] text-[13px] font-mono text-acc">
          {n.v}
        </code>
      );
      case "math":   return <KatexSpan key={i} body={n.v} />;
      case "link":   return (
        <a
          key={i}
          href={n.href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-pri underline underline-offset-2 decoration-pri/40 hover:decoration-pri"
        >
          {renderInline(n.v)}
        </a>
      );
    }
  });
}

function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  let i = 0;

  const pushText = (s: string) => {
    if (!s) return;
    const last = out[out.length - 1];
    if (last && last.t === "text") last.v += s;
    else out.push({ t: "text", v: s });
  };

  while (i < src.length) {
    const ch = src[i];

    // Inline math: $...$ (not $$) or \(...\)
    if (ch === "$" && src[i + 1] !== "$") {
      const end = src.indexOf("$", i + 1);
      if (end > i && end - i > 1) {
        const body = src.slice(i + 1, end).trim();
        if (body) {
          out.push({ t: "math", v: body });
          i = end + 1;
          continue;
        }
      }
    }
    if (ch === "\\" && src[i + 1] === "(") {
      const end = src.indexOf("\\)", i + 2);
      if (end > i && end - i > 2) {
        const body = src.slice(i + 2, end).trim();
        if (body) {
          out.push({ t: "math", v: body });
          i = end + 2;
          continue;
        }
      }
    }

    // Inline code: `...`
    if (ch === "`") {
      const end = src.indexOf("`", i + 1);
      if (end > i) {
        out.push({ t: "code", v: src.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }

    // Bold: **...**
    if (ch === "*" && src[i + 1] === "*") {
      const end = src.indexOf("**", i + 2);
      if (end > i) {
        out.push({ t: "bold", v: parseInline(src.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    }

    // Italic: *...*  (no debe ser **)
    if (ch === "*" && src[i + 1] !== "*") {
      const end = src.indexOf("*", i + 1);
      if (end > i && src[end + 1] !== "*") {
        out.push({ t: "italic", v: parseInline(src.slice(i + 1, end)) });
        i = end + 1;
        continue;
      }
    }

    // Link: [text](url)
    if (ch === "[") {
      const closeText = src.indexOf("]", i + 1);
      if (closeText > i && src[closeText + 1] === "(") {
        const closeUrl = src.indexOf(")", closeText + 2);
        if (closeUrl > closeText) {
          const linkText = src.slice(i + 1, closeText);
          const href = src.slice(closeText + 2, closeUrl).trim();
          // Solo permitimos http(s) y mailto. Bloquea javascript:.
          if (/^(https?:|mailto:)/.test(href)) {
            out.push({ t: "link", v: parseInline(linkText), href });
            i = closeUrl + 1;
            continue;
          }
        }
      }
    }

    // Auto-link de URLs sueltas http://... https://...
    if (ch === "h" && (src.startsWith("http://", i) || src.startsWith("https://", i))) {
      const m = /^https?:\/\/[^\s<>)]+/.exec(src.slice(i));
      if (m) {
        out.push({ t: "link", v: [{ t: "text", v: m[0] }], href: m[0] });
        i += m[0].length;
        continue;
      }
    }

    pushText(ch);
    i++;
  }
  return out;
}

/* ─── Code block con botón Copiar ───────────────────────────────────── */

function CodeBlock({ lang, body }: { lang: string; body: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore — algunos Webviews bloquean clipboard sin user gesture */
    }
  }

  return (
    <div className="relative rounded-lg border border-white/[0.06] bg-bg/40 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/[0.06] bg-white/[0.02]">
        <span className="text-[10px] uppercase tracking-[0.22em] text-muted font-mono">
          {lang || "code"}
        </span>
        <button
          onClick={copy}
          className="text-[10px] uppercase tracking-[0.18em] text-text-dim hover:text-text transition-colors"
        >
          {copied ? "✓ copiado" : "copiar"}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto scrollbar-thin text-[13px] leading-relaxed font-mono text-text">
        <code>{body}</code>
      </pre>
    </div>
  );
}

/* ─── KaTeX — safe math rendering ──────────────────────────────────── */

function renderMath(latex: string, displayMode: boolean): string {
  try {
    return katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      strict: false,
      trust: true,
    });
  } catch {
    return `<code class="text-danger text-xs">[math error]</code>`;
  }
}

function KatexSpan({ body }: { body: string }) {
  const html = useMemo(() => renderMath(body, false), [body]);
  return <span className="inline-katex" dangerouslySetInnerHTML={{ __html: html }} />;
}

function KatexDisplay({ body }: { body: string }) {
  const html = useMemo(() => renderMath(body, true), [body]);
  return (
    <div className="my-4 overflow-x-auto scrollbar-thin text-center">
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}
