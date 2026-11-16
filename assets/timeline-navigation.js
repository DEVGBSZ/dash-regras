(function () {
  let drag = null;
  let suppressClick = false;
  let fieldsCollapsed = false;

  function setButton(button, label, pressed, title) {
    if (!button) return;
    if (button.textContent !== label) button.textContent = label;
    if (button.getAttribute("aria-pressed") !== String(pressed)) button.setAttribute("aria-pressed", String(pressed));
    if (button.title !== title) button.title = title;
  }

  function syncTimelineControls(dialog) {
    if (!dialog) return;
    dialog.classList.toggle("timeline-fields-collapsed", fieldsCollapsed);
    setButton(
      dialog.querySelector("#timeline-fields-toggle"),
      fieldsCollapsed ? "Exibir campos" : "Minimizar campos",
      fieldsCollapsed,
      fieldsCollapsed ? "Exibir as colunas de detalhes" : "Recolher as colunas de detalhes"
    );
    const groups = Array.from(dialog.querySelectorAll(".gantt-group"));
    const allExpanded = groups.length > 0 && groups.every(function (group) { return group.open; });
    setButton(
      dialog.querySelector("#timeline-groups-toggle"),
      allExpanded ? "Fechar todos" : "Expandir todos",
      allExpanded,
      allExpanded ? "Recolher todos os responsáveis" : "Abrir todos os responsáveis"
    );
  }

  function showStartOfYear(table) {
    if (!table || table.dataset.positionedYear === table.dataset.timelineYear) return;
    table.scrollLeft = 0;
    table.dataset.positionedYear = table.dataset.timelineYear;
  }

  function positionAll() {
    document.querySelectorAll(".timeline-dialog .gantt-table").forEach(showStartOfYear);
    document.querySelectorAll(".timeline-dialog").forEach(syncTimelineControls);
  }

  new MutationObserver(function () {
    window.requestAnimationFrame(positionAll);
  }).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("load", function () { window.requestAnimationFrame(positionAll); });

  document.addEventListener("click", function (event) {
    const fieldsButton = event.target.closest("#timeline-fields-toggle");
    if (fieldsButton) {
      fieldsCollapsed = !fieldsCollapsed;
      syncTimelineControls(fieldsButton.closest(".timeline-dialog"));
      return;
    }
    const groupsButton = event.target.closest("#timeline-groups-toggle");
    if (!groupsButton) return;
    const dialog = groupsButton.closest(".timeline-dialog");
    const groups = Array.from(dialog.querySelectorAll(".gantt-group"));
    const shouldExpand = groups.some(function (group) { return !group.open; });
    groups.forEach(function (group) { group.open = shouldExpand; });
    syncTimelineControls(dialog);
  });

  document.addEventListener("toggle", function (event) {
    if (!event.target.matches(".timeline-dialog .gantt-group")) return;
    window.requestAnimationFrame(function () {
      syncTimelineControls(event.target.closest(".timeline-dialog"));
    });
  }, true);

  document.addEventListener("wheel", function (event) {
    const calendar = event.target.closest(".timeline-dialog .gantt-table");
    if (!calendar) return;
    const horizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY) || event.shiftKey;
    if (!horizontal) return;
    const movement = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    if (Math.abs(movement) < 2) return;
    event.preventDefault();
    calendar.scrollLeft += movement;
  }, { passive: false });

  document.addEventListener("pointerdown", function (event) {
    const surface = event.target.closest(".timeline-dialog .gantt-track, .timeline-dialog .gantt-axis");
    if (!surface || event.button !== 0) return;
    const calendar = surface.closest(".gantt-table");
    drag = { x: event.clientX, startScroll: calendar.scrollLeft, pointerId: event.pointerId, surface: surface, calendar: calendar, moved: false };
    surface.setPointerCapture(event.pointerId);
  });

  document.addEventListener("pointermove", function (event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const distance = event.clientX - drag.x;
    if (Math.abs(distance) > 4) drag.moved = true;
    drag.calendar.scrollLeft = drag.startScroll - distance;
    if (drag.moved) event.preventDefault();
  });

  document.addEventListener("pointerup", function (event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const moved = drag.moved;
    drag = null;
    if (moved) suppressClick = true;
  });

  document.addEventListener("pointercancel", function () { drag = null; });

  document.addEventListener("click", function (event) {
    if (!suppressClick || !event.target.closest(".timeline-dialog .gantt-table")) return;
    suppressClick = false;
    event.preventDefault();
    event.stopPropagation();
  }, true);
}());
