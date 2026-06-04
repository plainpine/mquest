// static/js/main.js

document.addEventListener("DOMContentLoaded", function () {
  // ページごとの処理分岐
  const page = document.body.dataset.page;

  if (page === "quest_run") {
    setupQuestForm();
  }

  // 自動的に .markdown クラスの要素をレンダリング
  document.querySelectorAll('.markdown[data-content]').forEach(div => {
    window.renderMarkdown(div, div.getAttribute('data-content'));
  });
});

/**
 * Markdown, Mermaid, MathJax をレンダリングするグローバル関数
 * @param {HTMLElement} element - レンダリング対象の要素
 * @param {string} text - レンダリングするテキスト
 */
window.renderMarkdown = async function(element, text) {
    if (!element) return;
    if (typeof marked === 'undefined') {
        element.textContent = text;
        return;
    }

    // marked のオプション設定
    if (marked.use) {
        marked.use({ gfm: true, breaks: true });
    } else if (marked.setOptions) {
        marked.setOptions({ gfm: true, breaks: true });
    }
    
    let content = text || '';
    // 改行コードの正規化 (LaTeXの \ne などが破壊されないよう、数式ブロック内は除外して置換)
    content = content.replace(/(\$\$[\s\S]*?\$\$|\$[\s\S]*?\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))|(\\n)/g, (match, math, newline) => {
        if (math) return math;
        return '\n';
    });
    element.innerHTML = marked.parse(content);

    // Mermaid の処理
    if (typeof mermaid !== 'undefined') {
        // marked が出力する可能性がある複数の形式に対応
        const mermaidBlocks = element.querySelectorAll('pre code.language-mermaid, pre code.lang-mermaid, pre.mermaid, div.mermaid');
        for (let block of mermaidBlocks) {
            let code = block.textContent.trim();
            let container;
            
            if (block.tagName.toLowerCase() === 'div' || (block.tagName.toLowerCase() === 'pre' && block.classList.contains('mermaid'))) {
                container = block;
            } else {
                // pre code の場合は pre を div に置き換える
                const pre = block.closest('pre');
                const div = document.createElement('div');
                div.className = 'mermaid';
                pre.parentElement.replaceChild(div, pre);
                container = div;
            }

            try {
                const { render } = mermaid;
                const id = 'mermaid-svg-' + Math.random().toString(36).substr(2, 9);
                const { svg } = await render(id, code);
                container.innerHTML = svg;
                // コンテナのクラスを更新して再描画を防ぐ（オプション）
                container.classList.add('mermaid-rendered');
            } catch (e) {
                console.error('Mermaid render error:', e);
                container.innerHTML = '<pre class="text-danger">Mermaid Error: ' + e.message + '</pre>';
            }
        }
    }

    // MathJax の処理
    if (window.MathJax && MathJax.typesetPromise) {
        try {
            await MathJax.typesetPromise([element]);
        } catch (e) {
            console.error('MathJax error:', e);
        }
    }
};

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