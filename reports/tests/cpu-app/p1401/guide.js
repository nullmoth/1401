// One step at a time with Back and Next, like the Probe app. "Show all the steps" puts every step on one page.
// The markup renders every step visible and the step list is plain #anchors, so with scripts off it all still works.
document.querySelectorAll(".app").forEach(function (app) {
  var pages = app.querySelectorAll(".pg"), navs = app.querySelectorAll(".nav");
  var back = app.querySelector(".back"), next = app.querySelector(".next"), all = app.querySelector(".all");
  var status = app.querySelector(".where");
  var cur = 0, every = false;

  function show(i, focus) {
    cur = Math.max(0, Math.min(pages.length - 1, i));
    pages.forEach(function (p, j) { p.hidden = !every && j !== cur; });
    navs.forEach(function (n, j) {
      if (j === cur && !every) n.setAttribute("aria-current", "step"); else n.removeAttribute("aria-current");
    });
    back.disabled = every || cur === 0;
    next.disabled = every || cur === pages.length - 1;
    all.setAttribute("aria-pressed", every ? "true" : "false");
    status.textContent = every ? "All " + pages.length + " steps" : "Step " + (cur + 1) + " of " + pages.length;
    all.textContent = every ? "Show one step at a time" : "Show all the steps on one page";
    if (focus) {
      var h = pages[cur].querySelector("h2");
      h.focus({ preventScroll: true });
      if (app.getBoundingClientRect().top < 0) pages[cur].scrollIntoView({ block: "start" });
    }
  }

  navs.forEach(function (n, j) {
    n.addEventListener("click", function (e) {
      e.preventDefault();
      if (every) pages[j].scrollIntoView({ block: "start" });
      else show(j, true);
    });
  });
  back.addEventListener("click", function () { show(cur - 1, true); });
  next.addEventListener("click", function () { show(cur + 1, true); });
  all.addEventListener("click", function () { every = !every; show(cur, false); });
  show(0, false);
});
