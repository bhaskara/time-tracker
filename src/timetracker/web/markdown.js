// A small Markdown renderer for the working memory. Builds DOM nodes directly
// (never innerHTML), so note text cannot inject markup.
//
// Supported: # headings, **bold**, *italic*, ~~strike~~, `code`, fenced code
// blocks, [links](https://...), bulleted and numbered lists (indent to nest
// visually), - [ ] task items, > quotes, --- dividers. Anything else is shown
// as plain paragraphs with line breaks kept.
"use strict";

function mdElement(tag, parent, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  parent.append(node);
  return node;
}

function mdInline(text, parent) {
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(~~[^~]+~~)|(\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parent.append(text.slice(last, match.index));
    const token = match[0];
    if (match[1]) mdElement("code", parent, token.slice(1, -1));
    else if (match[2]) mdInline(token.slice(2, -2), mdElement("strong", parent));
    else if (match[3]) mdInline(token.slice(1, -1), mdElement("em", parent));
    else if (match[4]) mdInline(token.slice(2, -2), mdElement("del", parent));
    else {
      const link = mdElement("a", parent, token.slice(1, token.indexOf("](")));
      link.href = match[6];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) parent.append(text.slice(last));
}

// Render Markdown `text` into `container`, replacing its contents. If
// `onToggle` is given, task checkboxes are clickable and call
// onToggle(lineIndex) with the index of their source line.
function renderMarkdown(text, container, onToggle) {
  container.replaceChildren();
  const lines = text.split("\n");
  const listItem = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  let paragraph = null;
  let list = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let match;
    if (line.trimStart().startsWith("```")) {
      const code = [];
      for (i++; i < lines.length && !lines[i].trimStart().startsWith("```"); i++) code.push(lines[i]);
      mdElement("code", mdElement("pre", container), code.join("\n"));
      paragraph = list = null;
    } else if ((match = /^(#{1,4})\s+(.*)$/.exec(line))) {
      mdInline(match[2], mdElement(`h${match[1].length + 2}`, container));
      paragraph = list = null;
    } else if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      mdElement("hr", container);
      paragraph = list = null;
    } else if ((match = listItem.exec(line))) {
      const ordered = /\d/.test(match[2]);
      const tag = ordered ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase() !== tag) list = mdElement(tag, container);
      const item = mdElement("li", list);
      const depth = Math.floor(match[1].length / 2);
      if (depth) item.style.marginLeft = `${depth * 1.4}em`;
      if (ordered) item.value = parseInt(match[2], 10);
      const task = /^\[( |x|X)\]\s+(.*)$/.exec(match[3]);
      if (task) {
        item.className = "task";
        const box = mdElement("input", item);
        box.type = "checkbox";
        box.checked = task[1] !== " ";
        if (onToggle) box.addEventListener("click", (event) => { event.stopPropagation(); onToggle(i); });
        else box.disabled = true;
        const body = mdElement("span", item);
        if (box.checked) body.className = "done";
        mdInline(task[2], body);
      } else {
        mdInline(match[3], item);
      }
      paragraph = null;
    } else if ((match = /^>\s?(.*)$/.exec(line))) {
      mdInline(match[1], mdElement("blockquote", container));
      paragraph = list = null;
    } else if (!line.trim()) {
      paragraph = list = null;
    } else {
      if (paragraph) mdElement("br", paragraph);
      else paragraph = mdElement("p", container);
      mdInline(line, paragraph);
      list = null;
    }
  }
}

// Flip the task checkbox on line `lineIndex` of Markdown `text`.
function toggleTaskLine(text, lineIndex) {
  const lines = text.split("\n");
  const line = lines[lineIndex];
  lines[lineIndex] = /\[ \]/.test(line) ? line.replace("[ ]", "[x]") : line.replace(/\[[xX]\]/, "[ ]");
  return lines.join("\n");
}
