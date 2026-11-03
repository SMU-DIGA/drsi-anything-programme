---
title: Progress
permalink: /progress/
---

# Progress

Dated updates on the programme, newest first. Each entry is a Markdown file in
[`_posts/`](https://github.com/{{ site.repository }}/tree/main/_posts).

<ul class="log">
{% for post in site.posts %}
  <li>
    <time datetime="{{ post.date | date_to_xmlschema }}">{{ post.date | date: "%Y-%m-%d" }}</time>
    · <a class="title" href="{{ post.url | relative_url }}">{{ post.title }}</a>
    {% for tag in post.tags %}<span class="tag">{{ tag }}</span>{% endfor %}
    <p class="summary">{{ post.summary }}</p>
  </li>
{% endfor %}
</ul>
