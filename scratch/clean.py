import re

with open('web/templates/dashboard.html', encoding='utf-8') as f:
    text = f.read()

text = text.replace('<?php echo htmlspecialchars($user_name); ?>', '{{ user.FIRSTNAME }} {{ user.LASTNAME }}')
text = text.replace('<?php echo htmlspecialchars($user_type); ?>', '{{ user.USER_TYPE }}')
text = text.replace('<?= count($db_pests) ?>', '{{ db_pests|length }}')
text = re.sub(r'<\?=\s*implode[^>]+>\?>', '', text)
text = re.sub(r'<\?php if \(\$message\): \?>.*?<\?php endif; \?>', '', text, flags=re.DOTALL)
text = text.replace('<?php if (empty($pests)): ?>', '{% if db_pests|length == 0 %}')
text = text.replace('<?php else: ?>', '{% else %}')
text = text.replace('<?php foreach ($pests as $p): ?>', '{% for p in db_pests %}')
text = text.replace("<?= $p['ID'] ?>", "{{ p.ID }}")
text = text.replace("<?= htmlspecialchars($p['PEST']) ?>", "{{ p.PEST }}")
text = text.replace("<?= htmlspecialchars(substr($p['DESCRIPTION'], 0, 50)) ?><?= strlen($p['DESCRIPTION']) > 50 ? '' : '' ?>", "{{ p.DESCRIPTION[:50] }}")
text = text.replace("<?= htmlspecialchars(substr($p['SUGGESTED_ACTION'], 0, 40)) ?><?= strlen($p['SUGGESTED_ACTION']) > 40 ? '' : '' ?>", "{{ p.SUGGESTED_ACTION[:40] }}")
text = text.replace("<?= htmlspecialchars($p['SIGNAL_RANGE']) ?>", "{{ p.SIGNAL_RANGE }}")
text = text.replace("<?= htmlspecialchars($p['IMAGE']) ?>", "{{ p.IMAGE }}")
text = re.sub(r'onclick=\"editPest[^"]+\"', 'onclick="editPest({{ p.ID }}, \'{{ p.PEST }}\', \'{{ p.DESCRIPTION }}\', \'{{ p.SUGGESTED_ACTION }}\', \'{{ p.SIGNAL_RANGE }}\', \'{{ p.IMAGE }}\')"', text)
text = text.replace('<?php endif; ?>', '{% endif %}')
text = text.replace('<?php endforeach; ?>', '{% endfor %}')
text = text.replace('const pestDB = <?= json_encode($db_pests) ?>;', 'const pestDB = {{ db_pests | tojson }};')
text = text.replace('const targetPests = <?= json_encode($target_pests) ?>;', 'const targetPests = {{ db_pests | map(attribute="PEST") | list | tojson }};')

# Also fix the video tag
text = text.replace('<video id="video" autoplay playsinline></video>', '<img id="video" src="/video_feed" style="width: 100%; border-radius: 16px;">')

with open('web/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(text)

