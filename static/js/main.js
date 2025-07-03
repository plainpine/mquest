// static/js/main.js

document.addEventListener("DOMContentLoaded", function () {
  // ページごとの処理分岐
  const page = document.body.dataset.page;

  if (page === "quest_run") {
    setupQuestForm();
  }
});

function setupQuestForm() {
  const form = document.getElementById("quest-form");
  if (!form) return;

  form.addEventListener("submit", function (e) {
    const radios = form.querySelectorAll("input[type=radio]");
    let allAnswered = true;
    const questions = new Set();

    radios.forEach(radio => {
      questions.add(radio.name);
    });

    questions.forEach(q => {
      const checked = form.querySelector(`input[name='${q}']:checked`);
      if (!checked) allAnswered = false;
    });

    if (!allAnswered) {
      e.preventDefault();
      alert("すべての問題に答えてください。");
    }
  });
}