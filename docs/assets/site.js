// modAI landing page: the answer console and the step viewer. No dependencies, no network calls.
(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- Answer console -------------------------------------------------------------------------
  // Each example is a recorded answer from the staging system on the fictional Atlasnova
  // documents; the page replays it the way the product streams an answer, then shows its source.
  const consoleEl = document.querySelector("[data-console]");
  const data = document.getElementById("console-data");
  if (consoleEl && data) {
    const examples = JSON.parse(data.textContent);
    const tabs = [...consoleEl.querySelectorAll("[role=tab]")];
    const question = consoleEl.querySelector("[data-question]");
    const answer = consoleEl.querySelector("[data-answer]");
    const evidence = consoleEl.querySelector("[data-evidence]");
    let timer = 0;

    const renderEvidence = (example) => {
      const source = example.source;
      evidence.classList.toggle("evidence--none", !source.document);
      evidence.querySelector("[data-evidence-label]").textContent = source.label;
      evidence.querySelector("[data-evidence-doc]").textContent = source.document || source.none;
      const quote = evidence.querySelector("[data-evidence-quote]");
      quote.replaceChildren();
      if (source.text) {
        const p = document.createElement("p");
        p.textContent = source.text;
        quote.append(p);
      }
      if (source.rows) {
        const table = document.createElement("table");
        for (const row of source.rows) {
          const tr = document.createElement("tr");
          if (row.match) tr.className = "match";
          for (const cell of row.cells) {
            const td = document.createElement("td");
            td.textContent = cell;
            tr.append(td);
          }
          table.append(tr);
        }
        quote.append(table);
      }
    };

    const show = (index, animate) => {
      const example = examples[index];
      tabs.forEach((tab, i) => {
        tab.setAttribute("aria-selected", String(i === index));
        tab.tabIndex = i === index ? 0 : -1;
      });
      window.clearTimeout(timer);
      question.textContent = example.question;
      renderEvidence(example);
      if (!animate || reduceMotion) {
        answer.textContent = example.answer;
        evidence.hidden = false;
        return;
      }
      evidence.hidden = true;
      const words = example.answer.split(" ");
      const caret = document.createElement("span");
      caret.className = "caret";
      caret.setAttribute("aria-hidden", "true");
      let shown = 0;
      answer.textContent = "";
      answer.append(caret);
      const step = () => {
        shown += 1;
        answer.textContent = words.slice(0, shown).join(" ");
        if (shown < words.length) {
          answer.append(caret);
          timer = window.setTimeout(step, 55);
        } else {
          timer = window.setTimeout(() => { evidence.hidden = false; }, 160);
        }
      };
      timer = window.setTimeout(step, 380);
    };

    // Reserve the height of the tallest example so switching questions never shifts the page.
    const exchange = consoleEl.querySelector(".exchange");
    const reserveHeight = () => {
      const current = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
      exchange.style.minHeight = "";
      let tallest = 0;
      examples.forEach((example) => {
        question.textContent = example.question;
        answer.textContent = example.answer;
        renderEvidence(example);
        tallest = Math.max(tallest, exchange.offsetHeight);
      });
      exchange.style.minHeight = `${tallest}px`;
      if (current >= 0) show(current, false);
    };
    let resizeTimer = 0;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(reserveHeight, 200);
    });
    // Measure first (fonts change line breaks), then play the opening answer once.
    (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => { reserveHeight(); show(0, true); });

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => show(index, true));
      tab.addEventListener("keydown", (event) => {
        const move = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
        if (!move) return;
        event.preventDefault();
        const next = (index + move + tabs.length) % tabs.length;
        tabs[next].focus();
        show(next, true);
      });
    });
  }

  // --- Step viewer (desktop): the selected step's screenshot -----------------------------------
  const stepButtons = [...document.querySelectorAll("[data-step]")];
  const figures = [...document.querySelectorAll("[data-step-figure]")];
  const selectStep = (index) => {
    stepButtons.forEach((button, i) => {
      button.setAttribute("aria-selected", String(i === index));
      button.tabIndex = i === index ? 0 : -1;
    });
    figures.forEach((figure, i) => { figure.hidden = i !== index; });
  };
  stepButtons.forEach((button, index) => {
    button.addEventListener("click", () => selectStep(index));
    button.addEventListener("keydown", (event) => {
      const move = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key];
      if (!move) return;
      event.preventDefault();
      const next = (index + move + stepButtons.length) % stepButtons.length;
      stepButtons[next].focus();
      selectStep(next);
    });
  });
  if (stepButtons.length) selectStep(0);

  // --- Mobile menu: close after choosing a link -------------------------------------------------
  document.querySelectorAll(".menu a").forEach((link) => {
    link.addEventListener("click", () => link.closest("details").removeAttribute("open"));
  });
})();
