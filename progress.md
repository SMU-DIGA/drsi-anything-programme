---
title: Progress
permalink: /progress/
summary: Dated updates on the programme, newest first.
---

<ol class="timeline">
{% for post in site.posts %}
  <li>
    <time datetime="{{ post.date | date_to_xmlschema }}">{{ post.date | date: "%b %-d, %Y" }}</time>
    <a class="tl-title" href="{{ post.url | relative_url }}">{{ post.title }}</a>
    <p>{{ post.summary }}</p>
    {% if post.tags.size > 0 %}<p class="tags">{% for tag in post.tags %}<span class="tag">{{ tag }}</span>{% endfor %}</p>{% endif %}
  </li>
{% endfor %}
</ol>
