import re
import os

file_path = 'D:\\yousystem\\Python\\mquest\\templates\\quest_run.html'

# 1. ファイルの内容を読み込む
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 2. 置き換え対象のブロックを特定
# {% elif question.type == 'numeric' %} から 最後の {% endif %} まで
# ただし、{% elif question.type == 'fill_in_the_blank_en' %} の前の {% endif %} よりも手前
# (fill_in_the_blank_en はそのまま残すため)
# regex を使用して、{% elif question.type == 'numeric' %} から {% elif question.type == 'fill_in_the_blank_en' %} の直前までを抽出
pattern = re.compile(r'{% elif question\.type == \'numeric\' %}.*?{% elif question\.type == \'fill_in_the_blank_en\' %}', re.DOTALL)
match = pattern.search(content)

if match:
    old_block_start_index = match.start()
    old_block_end_index = match.end() - len('{% elif question.type == \'fill_in_the_blank_en\' %}') # fill_in_the_blank_en の開始タグは含まない

    # 置き換える新しいブロックのコンテンツ
    new_block = """      {% elif question.type == 'numeric' or question.type == 'svg_interactive' or question.type == 'function_graph' %}
        {% if question.type == 'svg_interactive' %}
          <div class="svg-interactive-container" data-question-index="{{ q_index }}">
            {{ question.svg_content | safe }}
          </div>
        {% elif question.type == 'function_graph' %}
          <div class="function-graph-container" data-functions='{{ question.answers | tojson }}'>
            <div id="graph-target-{{ q_index }}"></div>
            <div class="graph-legend" id="graph-legend-{{ q_index }}"></div>
          </div>
        {% endif %}

        {% for ans in question.answers %}
          <div class="numeric-block" style="margin-top: 1rem;">
            <label class="markdown" data-content="{{ ans.caption | e }}"></label>
            <input type="text" name="q{{ q_index }}_answer{{ loop.index0 }}" class="numeric-input" data-qid="{{ q_index }}" readonly>
          </div>
        {% endfor %}

        {% if question.extra_body %}
          {% for extra_item in question.extra_body %}
            <div class="extra-body-item-renderer" style="margin-top: 2rem;">
              <div class="markdown" data-content="{{ extra_item.text | e }}"></div>
              {% for extra_ans in extra_item.answers %}
                <div class="numeric-block" style="margin-top: 1rem;">
                  <label class="markdown" data-content="{{ extra_ans.caption | e }}"></label>
                  <input type="text" name="q{{ q_index }}_extra_{{ loop.parent.index0 }}_answer{{ loop.index0 }}" class="numeric-input" data-qid="{{ q_index }}" readonly>
                </div>
              {% endfor %}
            </div>
          {% endfor %}
        {% endif %}

        <div style="height: 1rem;"></div>
        <div class="keypad" data-qid="{{ q_index }}" style="display: none;">
          <div class="keyboard-row">
            <button type="button" class="key-btn" data-num="1">1</button>
            <button type="button" class="key-btn" data-num="2">2</button>
            <button type="button" class="key-btn" data-num="3">3</button>
          </div>
          <div class="keyboard-row">
            <button type="button" class="key-btn" data-num="4">4</button>
            <button type="button" class="key-btn" data-num="5">5</button>
            <button type="button" class="key-btn" data-num="6">6</button>
          </div>
          <div class="keyboard-row">
            <button type="button" class="key-btn" data-num="7">7</button>
            <button type="button" class="key-btn" data-num="8">8</button>
            <button type="button" class="key-btn" data-num="9">9</button>
          </div>
          <div class="keyboard-row">
            <button type="button" class="key-btn" data-num="0">0</button>
            <button type="button" class="key-btn" data-num=".">.</button>
            <button type="button" class="key-btn" data-num="-">-</button>
            <button type="button" class="key-btn" data-num="/">/</button>
          </div>
          <div class="keyboard-row">
            <button type="button" class="key-btn" data-num="del">⌫</button>
            <button type="button" class="key-btn" data-num="clear">CL</button>
          </div>
        </div>
      {% elif question.type == 'fill_in_the_blank_en' %}(keep this part)"""

    # 古いブロックを新しいブロックで置き換える
    content = content[:old_block_start_index] + new_block + content[old_block_end_index:]
else:
    print("Target block not found in quest_run.html.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'{file_path} updated successfully.')
