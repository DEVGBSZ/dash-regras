(() => {
  const selector = "[data-native-rows]";
  const rendered = new WeakMap();
  function build(spec) {
    if (!Array.isArray(spec)) return document.createTextNode(spec ?? "");
    const [tag, props, children] = spec;
    const element = document.createElement(tag);
    for (const [name, value] of Object.entries(props)) {
      if (name === "style") Object.assign(element.style, value);
      else element.setAttribute(name === "className" ? "class" : name, value);
    }
    children.forEach(child => element.appendChild(build(child)));
    return element;
  }
  function render(host) {
    const source = host.dataset.nativeRows;
    if (rendered.get(host) === source) return;
    host.replaceChildren(build(JSON.parse(source)));
    rendered.set(host, source);
  }
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === "attributes") render(record.target);
      else for (const node of record.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.matches(selector)) render(node);
        else node.querySelectorAll(selector).forEach(render);
      }
    }
  }).observe(document.body, {subtree: true, childList: true, attributes: true,
                            attributeFilter: ["data-native-rows"]});
  document.querySelectorAll(selector).forEach(render);
  document.addEventListener("click", event => {
    const button = event.target.closest("button[data-issue-key]");
    if (button) dash_clientside.set_props("native-issue-click", {
      data: {key: button.dataset.issueKey, click: performance.now()}
    });
  });
})();
