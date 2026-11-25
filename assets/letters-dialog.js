(() => {
  document.addEventListener("click", (event) => {
    const dialog = document.getElementById("letters-dialog");
    if (!dialog) return;

    if (event.target.closest("#letters-open")) {
      event.preventDefault();
      if (!dialog.open) dialog.showModal();
      return;
    }

    if (event.target.closest("#letters-dialog-close")) {
      event.preventDefault();
      dialog.close();
    }
  });

  document.addEventListener("cancel", (event) => {
    if (event.target.id === "letters-dialog") event.target.close();
  });
})();
