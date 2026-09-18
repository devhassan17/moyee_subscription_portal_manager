/**
 * Moyee Coffee — Custom Odoo Frontend Utilities (Non-Tracking)
 * File: moyee_subscription_portal_manager/static/src/js/moyee_frontend_custom.js
 *
 * Contents:
 * 1. Timeline Scroller & Homepage Body Helper
 * 2. Chatter & Sale Order Communication Hiders
 * 3. Subscription Page Custom Rules (/my/subscriptions)
 * 4. Coffee Match Quiz Results Engine (Scoped exclusively to survey pages)
 */

(function () {
  "use strict";

  /* ============================================================
   * 1. HOMEPAGE HELPER & TIMELINE SCROLLER
   * ============================================================ */
  document.addEventListener("DOMContentLoaded", function () {
    if (window.location.pathname === "/") {
      document.body.classList.add("home-page");
    }

    const scroller = document.querySelector('.timeline');
    if (scroller) {
      const rootStyles = getComputedStyle(document.documentElement);
      const gapVal = parseFloat(rootStyles.getPropertyValue('--gap')) || 300;
      const rightArrow = document.querySelector('.arrow.right');
      const leftArrow = document.querySelector('.arrow.left');

      if (rightArrow) {
        rightArrow.addEventListener('click', function () {
          scroller.scrollBy({ left: gapVal, behavior: 'smooth' });
        });
      }
      if (leftArrow) {
        leftArrow.addEventListener('click', function () {
          scroller.scrollBy({ left: -gapVal, behavior: 'smooth' });
        });
      }
    }
  });

  /* ============================================================
   * 2. CHATTER & COMMUNICATION HIDE HELPERS
   * ============================================================ */
  document.addEventListener("DOMContentLoaded", function () {
    const saleComm = document.getElementById("sale_order_communication");
    if (saleComm) {
      saleComm.style.display = "none";
    }

    document.querySelectorAll('.o-mail-Chatter-top.position-sticky').forEach(function (el) {
      el.style.display = 'none';
    });
  });

  /* ============================================================
   * 3. ACTIVE SUBSCRIPTION PAGE HIDERS (/my/subscriptions)
   * ============================================================ */
  document.addEventListener("DOMContentLoaded", function () {
    if (!location.pathname.includes("/my/subscriptions")) return;

    const ACTIVE_STATUS = ["in progress", "in behandeling"];

    function isActiveSubscription() {
      const text = (document.body.innerText || "").toLowerCase();
      return ACTIVE_STATUS.some(word => text.includes(word));
    }

    function hideBlocks() {
      if (!isActiveSubscription()) return;

      // 1) Hide "Expected Payment / Verwachte betaling"
      const h = document.getElementById("quote_4");
      if (h) {
        const wrap = h.closest(".clearfix") || h.parentElement;
        if (wrap) wrap.style.setProperty("display", "none", "important");
      }

      // 2) Hide payment form
      const payForm = document.getElementById("o_payment_form");
      if (payForm) {
        const wrap2 = payForm.closest(".clearfix") || payForm.parentElement;
        if (wrap2) wrap2.style.setProperty("display", "none", "important");
      }

      // 3) Hide Automate Payment button
      const btnTexts = ["automate payment", "betaling automatiseren"];
      document.querySelectorAll("a.btn.btn-primary, button.btn.btn-primary").forEach(function (el) {
        const txt = (el.textContent || "").trim().toLowerCase();
        if (btnTexts.some(t => txt.includes(t))) {
          el.style.setProperty("display", "none", "important");
        }
      });

      // 4) Hide manage payment link
      document.querySelectorAll('a[href*="/my/payment_method"][href*="manage_subscription=True"]').forEach(function (a) {
        a.style.setProperty("display", "none", "important");
      });
    }

    hideBlocks();
    setTimeout(hideBlocks, 500);
    setTimeout(hideBlocks, 1500);

    const observer = new MutationObserver(hideBlocks);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  });

  /* ============================================================
   * 4. MOYEE COFFEE QUIZ RESULT ENGINE (SURVEY PAGES ONLY)
   * ============================================================ */
  (function () {
    // Hard guard: ONLY execute on survey/quiz paths
    if (!location.pathname.includes("/survey/") && !location.pathname.includes("768457b2")) return;

    var DEBUG = false;
    var QUIZ_TITLE = "5 QUESTIONS BETWEEN YOU AND YOUR BEST CUP EVER";
    var QUIZ_TOKEN = "768457b2-0387-43df-9824-81ebe4280328";
    var FALLBACK = "triple";

    var SCALE_MAP = {
      1: "int:light",
      2: "int:medium",
      3: "int:bold"
    };

    var COFFEES = {
      dark: {
        name: "Dark Roast",
        notes: "Donker gebrand, vol en krachtig. Weinig zuur, veel wakker.",
        taste: { int: 5, bit: 4, body: 5, acid: 1 },
        img: "https://www.moyeecoffee.com/web/image/product.template/7/image_1024",
        url: "https://www.moyeecoffee.com/shop?search=dark"
      },
      triple: {
        name: "Triple",
        notes: "Drie bonen, stevig en rijk. De klassieke bak.",
        taste: { int: 4, bit: 3, body: 4, acid: 2 },
        img: "https://www.moyeecoffee.com/web/image/product.template/6/image_1024",
        url: "https://www.moyeecoffee.com/shop?search=triple"
      },
      double: {
        name: "Double",
        notes: "Limu + Jimma, medium roast. Fruit en chocolade in balans.",
        taste: { int: 3, bit: 2, body: 4, acid: 3 },
        img: "https://www.moyeecoffee.com/web/image/product.template/5/image_1024",
        url: "https://www.moyeecoffee.com/shop?search=double"
      },
      single: {
        name: "Single Shot",
        notes: "Kenya single origin, lichter gebrand. Fruitig, bloemig, zijdezacht.",
        taste: { int: 3, bit: 1, body: 3, acid: 4 },
        img: "https://www.moyeecoffee.com/web/image/product.template/4/image_1024",
        url: "https://www.moyeecoffee.com/shop?search=single"
      },
      microlot: {
        name: "Microlot",
        notes: "Top 5% bonen. Verfijnd en complex, voor de kenner.",
        taste: { int: 2, bit: 1, body: 3, acid: 5 },
        img: "https://www.moyeecoffee.com/web/image/product.template/30/image_1024",
        url: "https://www.moyeecoffee.com/shop?search=microlot"
      },
      espresso_cap: {
        name: "Espresso capsules",
        notes: "Kort, krachtig, donker. Klaar in twintig seconden.",
        taste: { int: 5, bit: 4, body: 4, acid: 1 },
        img: "https://www.moyeecoffee.com/web/image/product.template/10/image_1024",
        url: "https://www.moyeecoffee.com/shop/capespresso25-espresso-capsules-10?category=2"
      },
      lungo_cap: {
        name: "Lungo capsules",
        notes: "Langer, zachter, ronder. Voor wie de dag rustig opbouwt.",
        taste: { int: 3, bit: 2, body: 3, acid: 3 },
        img: "https://www.moyeecoffee.com/web/image/product.template/9/image_1024",
        url: "https://www.moyeecoffee.com/shop/caplungo25-lungo-capsules-9?category=2"
      }
    };

    var RULES = [
      { key: "brew:capsules", words: ["capsule"], votes: {} },
      { key: "brew:espresso", words: ["espresso machine"], votes: { dark: 3, triple: 2, espresso_cap: 1 } },
      { key: "brew:auto", words: ["fullautomatic", "volautomaat"], votes: { triple: 2, double: 2 } },
      { key: "brew:slow", words: ["filter", "pour over", "aeropress", "french press", "moka"], votes: { single: 3, microlot: 3, double: 1 } },
      { key: "taste:full", words: ["full and bitter", "full & bitter", "bold and bitter", "bold & bitter", "vol en bitter", "wake me up"], votes: { dark: 3, triple: 3, espresso_cap: 3 } },
      { key: "taste:fruity", words: ["fruity", "fruitig", "sparkle", "bright"], votes: { single: 3, microlot: 3, double: 3, lungo_cap: 2 } },
      { key: "int:bold", words: ["bold", "strong & dark", "strong and dark", "sterk"], votes: { dark: 4, triple: 2, espresso_cap: 4 } },
      { key: "int:medium", words: ["medium"], votes: { triple: 3, double: 3, espresso_cap: 1, lungo_cap: 1 } },
      { key: "int:light", words: ["light", "mild", "licht", "smooth"], votes: { single: 3, microlot: 2, double: 2, lungo_cap: 4 } },
      { key: "style:adv", words: ["adventurous", "avontuurlijk", "microlot", "single origin"], votes: { microlot: 4, single: 3 } },
      { key: "style:classic", words: ["classic", "klassiek", "good stuff"], votes: { triple: 2, double: 2, dark: 2 } }
    ];

    var TIEBREAK = ["triple", "double", "dark", "single", "microlot"];
    var TIEBREAK_CAPS = ["espresso_cap", "lungo_cap"];

    function rankCoffees(matched) {
      var caps = !!matched["brew:capsules"];
      var pool = caps ? TIEBREAK_CAPS : TIEBREAK;
      var totals = {};
      pool.forEach(function (k) { totals[k] = 0; });

      matched.__rules.forEach(function (rule) {
        var v = rule.votes || {};
        Object.keys(v).forEach(function (k) {
          if (totals.hasOwnProperty(k)) totals[k] += v[k];
        });
      });

      return pool.slice().sort(function (a, b) {
        if (totals[b] !== totals[a]) return totals[b] - totals[a];
        return pool.indexOf(a) - pool.indexOf(b);
      });
    }

    var DIMS = [
      { k: "int", l: "Intensiteit" },
      { k: "bit", l: "Bitter" },
      { k: "body", l: "Body" },
      { k: "acid", l: "Aciditeit" }
    ];
    var SCALE = 5;

    function matrixTexts(doc) {
      var out = [];
      var tables = doc.querySelectorAll("table");
      for (var t = 0; t < tables.length; t++) {
        var table = tables[t];
        var headRow = table.querySelector("thead tr") || table.rows[0];
        if (!headRow) continue;
        var cells = table.querySelectorAll("td, th");
        for (var c = 0; c < cells.length; c++) {
          var cell = cells[c];
          var isSel = /selected/.test(cell.className) || cell.querySelector("input:checked");
          if (!isSel) continue;
          var head = headRow.cells[cell.cellIndex];
          var label = head ? (head.innerText || head.textContent || "").replace(/\s+/g, " ").trim() : "";
          if (label && out.indexOf(label) === -1) out.push(label);
        }
      }
      return out;
    }

    function extractAnswers(doc) {
      var found = {};
      var hitRules = [];
      var texts = matrixTexts(doc);

      var SELECTORS = [".o_survey_selected", ".o_survey_answer_selected", "input:checked", ".o_survey_question_matrix td.o_survey_selected", "[class*='selected']"];
      for (var s = 0; s < SELECTORS.length; s++) {
        var before = texts.length;
        var nodes = doc.querySelectorAll(SELECTORS[s]);
        if (!nodes.length) continue;
        for (var i = 0; i < nodes.length; i++) {
          var n = nodes[i];
          var t = (n.tagName === "INPUT") ? (n.closest("label") || doc.querySelector('label[for="' + n.id + '"]') || n.parentNode)?.innerText : n.innerText;
          t = (t || "").replace(/\s+/g, " ").trim();
          if (t && texts.indexOf(t) === -1) texts.push(t);
        }
        if (texts.length > before) break;
      }

      for (var j = 0; j < texts.length; j++) {
        var low = texts[j].toLowerCase();
        var claimed = false;

        if (/\d/.test(low) && !/[a-z]/.test(low)) {
          var v = parseInt(low.match(/\d+/)[0], 10);
          var lvl = SCALE_MAP[v] || "int:medium";
          for (var q = 0; q < RULES.length; q++) {
            if (RULES[q].key === lvl) {
              found[lvl] = texts[j];
              hitRules.push(RULES[q]);
              break;
            }
          }
          continue;
        }

        for (var r = 0; r < RULES.length && !claimed; r++) {
          for (var w = 0; w < RULES[r].words.length; w++) {
            if (low.indexOf(RULES[r].words[w]) !== -1) {
              found[RULES[r].key] = texts[j];
              hitRules.push(RULES[r]);
              claimed = true;
              break;
            }
          }
        }
      }
      found.__rules = hitRules;
      return { keys: found, texts: texts };
    }

    function injectCss() {
      if (document.getElementById("mm-font")) return;
      var f = document.createElement("link");
      f.id = "mm-font"; f.rel = "stylesheet";
      f.href = "https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&family=Roboto+Condensed:wght@400;700&display=swap";
      document.head.appendChild(f);

      var s = document.createElement("style");
      s.id = "mm-style";
      s.textContent = [
        '#moyee-match{--pink:#E5007D;--ink:#1a1a1a;--muted:#6b6b6b;--line:#ececec;font-family:"Roboto Condensed",system-ui,sans-serif;color:var(--ink);max-width:960px;margin:8px auto 40px;padding:0 16px}',
        '#moyee-match *{box-sizing:border-box}',
        '#moyee-match .mm-hero{display:grid;grid-template-columns:200px 1fr;gap:28px;align-items:center;background:#fff;border:2px solid var(--pink);border-radius:14px;padding:24px;box-shadow:0 10px 30px rgba(229,0,125,.08)}',
        '#moyee-match .mm-hero img{width:100%;height:auto;display:block}',
        '#moyee-match .mm-eyebrow{font-family:"Oswald",sans-serif;font-weight:700;letter-spacing:.14em;text-transform:uppercase;font-size:12px;color:var(--pink);margin:0 0 6px}',
        '#moyee-match .mm-hero h3{font-family:"Oswald",sans-serif;font-weight:700;text-transform:uppercase;font-size:52px;line-height:.95;margin:0 0 12px}',
        '#moyee-match .mm-notes{font-size:18px;color:var(--muted);margin:0 0 14px}',
        '#moyee-match .mm-bar{display:flex;align-items:center;gap:10px;margin:6px 0}',
        '#moyee-match .mm-bar-l{width:92px;font-family:"Oswald",sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}',
        '#moyee-match .mm-bar-t{flex:1;height:8px;background:var(--line);border-radius:5px;overflow:hidden}',
        '#moyee-match .mm-bar-f{display:block;height:100%;background:var(--pink)}',
        '#moyee-match .mm-cta{display:inline-block;margin-top:14px;background:var(--pink);color:#fff;text-decoration:none;font-family:"Oswald",sans-serif;font-weight:700;text-transform:uppercase;letter-spacing:.06em;font-size:14px;padding:12px 22px;border-radius:8px}',
        '#moyee-match .mm-cta:hover{filter:brightness(1.05)}',
        '#moyee-match .mm-rest-title{font-family:"Oswald",sans-serif;font-weight:700;text-transform:uppercase;letter-spacing:.1em;font-size:13px;color:var(--muted);margin:32px 0 4px;padding-bottom:8px;border-bottom:1px solid var(--line)}',
        '#moyee-match .mm-legend{font-size:11px;color:var(--muted);margin:0 0 14px}',
        '#moyee-match .mm-rest{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}',
        '#moyee-match .mm-card{display:flex;flex-direction:column;padding:16px 14px;border:1px solid var(--line);border-radius:10px;background:#fff}',
        '#moyee-match .mm-card img{width:60px;height:auto;align-self:center;margin-bottom:10px}',
        '#moyee-match .mm-name{font-family:"Oswald",sans-serif;font-weight:700;text-transform:uppercase;font-size:15px;line-height:1.05;margin:0 0 8px}',
        '#moyee-match .mm-mini{display:flex;align-items:center;gap:6px;margin:4px 0}',
        '#moyee-match .mm-mini-l{width:60px;font-size:10px;text-transform:uppercase;color:var(--muted)}',
        '#moyee-match .mm-mini-t{position:relative;flex:1;height:6px;background:var(--line);border-radius:4px}',
        '#moyee-match .mm-mini-f{position:absolute;left:0;top:0;height:100%;background:var(--pink);border-radius:4px}',
        '#moyee-match .mm-mini-k{position:absolute;top:-2px;width:2px;height:10px;background:var(--ink);transform:translateX(-1px)}',
        '#moyee-match .mm-card a{margin-top:12px;color:var(--pink);text-decoration:none;font-weight:700;font-size:13px;text-transform:uppercase}',
        '@media(max-width:720px){#moyee-match .mm-hero{grid-template-columns:110px 1fr;gap:16px;padding:18px}#moyee-match .mm-hero h3{font-size:34px}#moyee-match .mm-rest{grid-template-columns:1fr}}'
      ].join("");
      document.head.appendChild(s);
    }

    function heroBars(t) {
      return DIMS.map(function (d) {
        return '<div class="mm-bar"><span class="mm-bar-l">' + d.l + '</span><span class="mm-bar-t"><span class="mm-bar-f" style="width:' + (t[d.k] / SCALE * 100) + '%"></span></span></div>';
      }).join("");
    }

    function miniBars(t, ref) {
      return DIMS.map(function (d) {
        return '<div class="mm-mini"><span class="mm-mini-l">' + d.l + '</span><span class="mm-mini-t"><span class="mm-mini-f" style="width:' + (t[d.k] / SCALE * 100) + '%"></span><span class="mm-mini-k" style="left:' + (ref[d.k] / SCALE * 100) + '%"></span></span></div>';
      }).join("");
    }

    function esc(s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    function renderQuiz(target, key, ranked) {
      if (!COFFEES[key]) key = FALLBACK;
      var existing = document.getElementById("moyee-match");
      if (existing && existing.getAttribute("data-key") === key) return;
      injectCss();

      var heads = target.querySelectorAll("h1,.display-1,.display-2,.display-3,.display-4");
      for (var hi = 0; hi < heads.length; hi++) {
        if (!heads[hi].closest("#moyee-match")) heads[hi].style.display = "none";
      }

      var match = COFFEES[key];
      var others = (ranked || []).filter(function (k) { return k !== key && COFFEES[k]; }).slice(0, 3).map(function (k) { return COFFEES[k]; });

      var box = document.createElement("div");
      box.id = "moyee-match";
      box.setAttribute("data-key", key);
      box.innerHTML =
        '<div class="mm-hero"><img src="' + match.img + '" alt="' + esc(match.name) + '"><div>' +
          '<p class="mm-eyebrow">Jouw match</p>' +
          '<h3>' + esc(match.name) + '</h3>' +
          '<p class="mm-notes">' + esc(match.notes) + '</p>' +
          '<div>' + heroBars(match.taste) + '</div>' +
          '<a class="mm-cta" href="' + match.url + '">Bekijk deze koffie</a>' +
        '</div></div>' +
        (others.length ? '<p class="mm-rest-title">Ook iets voor jou</p><div class="mm-rest">' + others.map(function (c) {
          return '<div class="mm-card"><img src="' + c.img + '" alt="' + esc(c.name) + '"><p class="mm-name">' + esc(c.name) + '</p><div>' + miniBars(c.taste, match.taste) + '</div><a href="' + c.url + '">Bekijk</a></div>';
        }).join("") + '</div>' : "");

      if (existing) {
        existing.parentNode.replaceChild(box, existing);
        return;
      }

      var btnRow = null;
      var links = target.querySelectorAll("a, button");
      for (var i = 0; i < links.length; i++) {
        var n = links[i];
        while (n && n.parentNode && n.parentNode !== target) n = n.parentNode;
        if (n && n.parentNode === target) { btnRow = n; break; }
      }
      if (btnRow) target.insertBefore(box, btnRow);
      else target.appendChild(box);
    }

    function bootQuiz() {
      var finished = document.querySelector(".o_survey_finished");
      if (!finished || document.getElementById("moyee-match") || window.__moyeeFetching) return;

      var form = document.querySelector("form[data-answer-token]");
      var token = form && form.getAttribute("data-answer-token");
      var surveyToken = form && form.getAttribute("data-survey-token");

      var pageTxt = ((document.title || "") + " " + (document.body.innerText || "")).toUpperCase();
      var isQuiz = surveyToken === QUIZ_TOKEN || pageTxt.indexOf(QUIZ_TITLE.toUpperCase()) !== -1 || location.pathname.indexOf(QUIZ_TOKEN) !== -1;
      if (!isQuiz) return;

      try { renderQuiz(finished, FALLBACK, TIEBREAK); } catch (e) {}

      if (!token || !surveyToken) return;

      window.__moyeeFetching = true;
      var url = "/survey/print/" + surveyToken + "?answer_token=" + token + "&review=True";
      fetch(url, { credentials: "same-origin" })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var doc = new DOMParser().parseFromString(html, "text/html");
          var res = extractAnswers(doc);
          if (!res.texts.length) return;
          var ranked = rankCoffees(res.keys);
          renderQuiz(finished, ranked[0], ranked);
        });
    }

    document.addEventListener("DOMContentLoaded", bootQuiz);
    setTimeout(bootQuiz, 1000);
  })();

})();
