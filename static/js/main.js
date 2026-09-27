// 传奇3 资料站 · 交互脚本
// 1. 列表页搜索过滤(按卡片 data-name)
// 2. 首页全局搜索(回车跳转到对应分类搜索)

(function () {
  "use strict";

  // 列表页检索 + Zircon 对照状态筛选
  var filterInput = document.querySelector(".filter-input");
  var filterButtons = document.querySelectorAll("[data-match-filter]");
  var filterCount = document.querySelector(".zircon-filter-count");
  if (filterInput || filterButtons.length) {
    var activeMatchFilter = "all";
    var cards = Array.prototype.slice.call(document.querySelectorAll(".group .data-card"));
    var totalCards = cards.length;

    function applyListFilters() {
      var q = filterInput ? filterInput.value.trim().toLowerCase() : "";
      var visibleCount = 0;
      cards.forEach(function (card) {
        var name = (card.getAttribute("data-name") || "").toLowerCase();
        var state = card.getAttribute("data-zircon-state") || "unreviewed";
        var matchesQuery = !q || name.indexOf(q) !== -1;
        var matchesState = activeMatchFilter === "all"
          || (activeMatchFilter === "review" && ["matched", "candidate", "conflict"].indexOf(state) !== -1)
          || (activeMatchFilter === "unmatched" && state === "unmatched")
          || (activeMatchFilter === "unreviewed" && state === "unreviewed");
        var show = matchesQuery && matchesState;
        card.classList.toggle("is-hidden", !show);
        if (show) visibleCount++;
      });
      document.querySelectorAll(".group").forEach(function (group) {
        var visible = group.querySelectorAll(".data-card:not(.is-hidden)").length;
        group.classList.toggle("empty-group", visible === 0);
      });
      if (filterCount) filterCount.textContent = "显示 " + visibleCount + " / " + totalCards + " 条";
    }

    if (filterInput) filterInput.addEventListener("input", applyListFilters);
    filterButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        activeMatchFilter = button.getAttribute("data-match-filter") || "all";
        filterButtons.forEach(function (item) {
          var active = item === button;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-pressed", active ? "true" : "false");
        });
        applyListFilters();
      });
    });
    applyListFilters();
  }

  // 首页全局搜索: 回车跳转
  var globalSearch = document.getElementById("global-search");
  if (globalSearch) {
    globalSearch.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      var q = this.value.trim();
      if (!q) return;
      var page = pickCategory(q);
      if (page) {
        location.href = page + "/index.html" + (q ? "#" : "");
      }
    });
  }

  // 依据关键词猜测分类页
  function pickCategory(q) {
    var mobWords = ["怪", "兽", "王", "蜘蛛", "骷髅", "僵尸", "蛇", "猪", "蜈蚣", "蚂蚁", "蝙蝠", "蝎子", "鹰", "狼", "鹿", "鸡", "羊", "牛", "神魔", "恶魔", "法老"];
    var itemWords = ["剑", "刀", "斧", "杖", "盔", "甲", "衣", "靴", "鞋", "戒指", "项链", "手镯", "头盔", "药", "金条", "肉", "套装", "饰品"];
    var skillWords = ["剑术", "掌", "火", "雷", "冰", "术", "法", "咒", "盾", "召唤", "战甲", "圣言"];
    var missionWords = ["任务", "奖励", "NPC"];
    var score = function (words) { return words.reduce(function (n, w) { return q.indexOf(w) !== -1 ? n + 1 : n; }, 0); };
    var scores = [
      ["mobs", score(mobWords)],
      ["items", score(itemWords)],
      ["skills", score(skillWords)],
      ["missions", score(missionWords)],
    ].sort(function (a, b) { return b[1] - a[1]; });
    return scores[0][1] > 0 ? scores[0][0] : null;
  }
})();
