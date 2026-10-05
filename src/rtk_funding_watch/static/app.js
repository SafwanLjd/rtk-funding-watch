/* RTK Funding Watch: client-side search and status filtering.
   No frameworks, no network. Operates on the server-rendered DOM, so the page
   is fully usable with JavaScript disabled. */

(function () {
  "use strict";

  var search = document.getElementById("search");
  var toggles = Array.prototype.slice.call(
    document.querySelectorAll(".filter-toggle input")
  );
  var cards = Array.prototype.slice.call(
    document.querySelectorAll(".call")
  );
  var count = document.getElementById("result-count");
  var empty = document.getElementById("empty-state");

  if (!cards.length) {
    return;
  }

  function activeStatuses() {
    var set = {};
    toggles.forEach(function (t) {
      if (t.checked) {
        set[t.value] = true;
      }
    });
    return set;
  }

  function apply() {
    var query = (search && search.value ? search.value : "")
      .trim()
      .toLowerCase();
    var statuses = activeStatuses();
    var visible = 0;

    cards.forEach(function (card) {
      var status = card.getAttribute("data-status") || "";
      var text = card.getAttribute("data-text") || "";
      var statusOk = statuses[status] === true;
      var queryOk = query === "" || text.indexOf(query) !== -1;
      var show = statusOk && queryOk;
      card.hidden = !show;
      if (show) {
        visible += 1;
      }
    });

    if (count) {
      var noun = visible === 1 ? "call" : "calls";
      count.textContent = visible + " " + noun + " shown";
    }
    if (empty) {
      empty.hidden = visible !== 0;
    }
  }

  if (search) {
    search.addEventListener("input", apply);
  }
  toggles.forEach(function (t) {
    t.addEventListener("change", apply);
  });

  apply();
})();
