<div align="center" dir="ltr">

<img src="apps/docs/public/brand/logo-texttocad-animated.svg" alt="text-to-cad" width="800">

<p> Give your agent CAD superpowers. </p>

[مستندات](https://www.texttocad.dev)

[![GitHub stars](https://img.shields.io/github/stars/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Stars)](https://github.com/earthtojake/text-to-cad/stargazers)
[![skills.sh](https://skills.sh/b/earthtojake/text-to-cad?style=for-the-badge)](https://skills.sh/b/earthtojake/text-to-cad)
[![Follow @earthtojake](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=for-the-badge&logo=x)](https://x.com/earthtojake)
[![Join Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5FGB9DwJYU)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/earthtojake/text-to-cad/test.yml?branch=main&style=for-the-badge&logo=githubactions&logoColor=white&label=Tests)](https://github.com/earthtojake/text-to-cad/actions/workflows/test.yml?query=branch%3Amain)
[![cadgen](https://img.shields.io/pypi/v/cadgen?style=for-the-badge&logo=pypi&logoColor=white&label=cadgen)](https://pypi.org/project/cadgen/)
[![build123d](https://img.shields.io/badge/build123d-0.11-2F6FB0?style=for-the-badge)](https://github.com/gumyr/build123d)
[![Open CASCADE](https://img.shields.io/badge/Open%20CASCADE-7.9-E2001A?style=for-the-badge)](https://dev.opencascade.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](packages/cadgen/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-20+-5FA04E?style=for-the-badge&logo=nodedotjs)](https://nodejs.org)

</div>

<h1 dir="rtl" align="right">text-to-cad</h1>

<p dir="rtl" align="right">افزونهٔ <code dir="ltr">text-to-cad</code> گردش‌کارهای محلی را در اختیار عامل هوش مصنوعی شما قرار می‌دهد تا مدل‌های سه‌بعدی را با فرمت‌های <code dir="ltr">STEP</code>، <code dir="ltr">GLB</code>، <code dir="ltr">STL</code> یا <code dir="ltr">3MF</code> تولید کند. این ابزار بررسی‌های مربوط به قابلیت ساخت محصول را نیز انجام می‌دهد، نقشه‌های مهندسی می‌سازد و به سرویس‌های متداول چاپ سه‌بعدی، ساخت ورق فلزی و تولید با دستگاه‌های <code dir="ltr">CNC</code> متصل می‌شود.</p>

<p dir="rtl" align="right">این ابزار با عامل‌های هوش مصنوعی محبوبی که از افزونه‌ها یا چارچوب <a href="https://skills.sh" dir="ltr">skills</a> پشتیبانی می‌کنند سازگار است؛ از جمله <code dir="ltr">Claude Code</code>، <code dir="ltr">Codex</code>، <code dir="ltr">Cursor</code>، <code dir="ltr">Gemini</code> و <code dir="ltr">Grok</code>.</p>

<h2 id="install" dir="rtl" align="right">💻 نصب</h2>

<h3 dir="rtl" align="right">روش پیشنهادی: از عامل هوش مصنوعی خود بخواهید</h3>

<p dir="rtl" align="right">این پیام را برای عامل خود بفرستید تا افزونهٔ <code dir="ltr">text-to-cad</code> را برایتان نصب کند.</p>

```text
Install text-to-cad from https://github.com/earthtojake/text-to-cad
```

<p dir="rtl" align="right">همچنین می‌توانید آن را به‌صورت دستی نصب کنید:</p>

<ol dir="rtl" align="right">
<li>اجرای CAD از طریق <a href="https://docs.astral.sh/uv/" dir="ltr">uv</a> انجام می‌شود. بررسی کنید که نصب شده باشد؛ دستور <code dir="ltr">uv --version</code> را اجرا کنید. اگر نصب نیست، آن را با <a href="https://docs.astral.sh/uv/getting-started/installation/" dir="ltr">نصب‌کنندهٔ uv</a> نصب کنید.</li>
<li>دستورهای بخش مربوط به برنامهٔ عامل خود را در ادامه اجرا کنید. اگر برنامهٔ شما در فهرست نیست، بخش <a href="#other-agents">سایر عامل‌ها</a> را ببینید.</li>
<li>برنامه را دوباره اجرا کنید. در اولین اجرا، محیط اجرایی CAD دانلود می‌شود؛ بنابراین اتصال اینترنت لازم است.</li>
</ol>

<p dir="rtl" align="right">افزونهٔ برنامهٔ عامل، مهارت‌ها، نمایشگر CAD و یک سرور محلی به نام <code dir="ltr">cadgen mcp</code> را در اختیار شما قرار می‌دهد. اگر عامل شما از افزونه پشتیبانی نمی‌کند، فقط مهارت‌ها را نصب کنید. در هر برنامه یکی از این دو روش را انتخاب کنید، نه هر دو؛ چون در غیر این صورت هر مهارت دو بار نصب می‌شود.</p>

<p dir="rtl" align="right">دستورهای نصب زیر از شاخهٔ <code dir="ltr">latest</code> استفاده می‌کنند. این شاخه فقط افزونه را در بر دارد و هر نسخه را پس از انتشار در <code dir="ltr">PyPI</code> دریافت می‌کند. شاخهٔ <code dir="ltr">main</code> که محل توسعه است نیز قابل نصب است، اما ممکن است تغییراتی داشته باشد که هنوز منتشر نشده‌اند. نام‌گذاری شاخه در برنامه‌های مختلف متفاوت است: <code dir="ltr">#latest</code>، <code dir="ltr">--ref latest</code>، <code dir="ltr">@latest</code> یا <code dir="ltr">--branch latest</code>. اگر آن را مشخص نکنید، برنامه شاخهٔ <code dir="ltr">main</code> را نصب می‌کند.</p>

<p dir="rtl" align="right">در بخش هر برنامه، روش به‌روزرسانی و نصب مجدد <code dir="ltr">text-to-cad</code> نیز توضیح داده شده است. برای نصب مجدد، ابتدا افزونه را حذف و سپس دوباره نصب کنید. با به‌روزرسانی افزونه، CAD نیز به‌روز می‌شود: نسخهٔ جدید <code dir="ltr">cadgen</code> هنگام اولین اجرا دانلود می‌شود و مهارت‌ها و سرور از همان نسخه استفاده می‌کنند. نسخه‌های قبلی تا زمانی که دستور <code dir="ltr">uv cache prune</code> را اجرا نکنید، در حافظهٔ نهان <code dir="ltr">uv</code> باقی می‌مانند.</p>

<h3 id="claude-code" dir="rtl" align="right">Claude Code</h3>

```bash
claude plugin marketplace add earthtojake/text-to-cad#latest
claude plugin install text-to-cad@earthtojake
```

<p dir="rtl" align="right">این افزونه سرور CAD را نیز راه‌اندازی می‌کند. اگر <code dir="ltr">Claude Code</code> بتواند نمای برنامه‌ها را نشان دهد، مدل‌ها را به‌شکل کارت‌های نمایشگر در گفت‌وگو نمایش می‌دهد. در محیط‌هایی که چنین نمایی در دسترس نیست، مانند ترمینال، با درخواست نمایش مدل پیوندی دریافت می‌کنید که مدل را در نمایشگر CAD مرورگر باز می‌کند.</p>

<p dir="rtl" align="right">برای به‌روزرسانی، دستورهای زیر را اجرا کنید و سپس <code dir="ltr">Claude Code</code> را دوباره راه‌اندازی کنید:</p>

```bash
claude plugin marketplace update earthtojake
claude plugin update text-to-cad@earthtojake
```

<p dir="rtl" align="right">برای نصب مجدد، ابتدا افزونه و بازارچهٔ آن را با دستورهای زیر حذف کنید و سپس دستورهای نصب را دوباره اجرا کنید:</p>

```bash
claude plugin uninstall text-to-cad@earthtojake
claude plugin marketplace remove earthtojake
```

<h3 id="claude-desktop" dir="rtl" align="right">Claude Desktop</h3>

<p dir="rtl" align="right">در گفت‌وگوی Claude می‌توانید درخواست کنید مدلی را نمایش دهد؛ مدل به‌شکل یک کارت نمایشگر ظاهر می‌شود که می‌توانید آن را بچرخانید، به درخواست خود اضافه کنید یا در اندازهٔ کامل باز کنید. Claude می‌تواند گزینه‌ای را که انتخاب کرده‌اید بخواند و همان چیزی را که شما می‌بینید مشاهده کند. ابزار به‌صورت محلی و از طریق <code dir="ltr">uv</code> اجرا می‌شود. سرور را از مسیر <code dir="ltr">Settings &gt; Developer &gt; Edit Config</code> به پیکربندی Claude Desktop اضافه کنید و سپس برنامه را دوباره راه‌اندازی کنید. اگر Claude Desktop نتوانست <code dir="ltr">uvx</code> را پیدا کند، مسیر کامل آن را با دستور <code dir="ltr">which uvx</code> پیدا کرده و وارد کنید.</p>

```json
{
  "mcpServers": {
    "cad": {
      "command": "uvx",
      "args": ["--no-config", "--managed-python", "--python", "3.13", "--from", "cadgen==0.7.15", "cadgen", "mcp"],
      "env": {"CADGEN_INSTALL_CHANNEL": "claude-desktop"}
    }
  }
}
```

<p dir="rtl" align="right">این پیکربندی، نسخهٔ مشخصی از <code dir="ltr">cadgen</code> را در آرگومان‌های <code dir="ltr">args</code> تثبیت می‌کند و <code dir="ltr">uvx</code> نیز همان نسخه‌ای را که نخست دانلود کرده است نگه می‌دارد. برای به‌روزرسانی، شمارهٔ نسخه را به <a href="https://pypi.org/project/cadgen/" dir="ltr">آخرین نسخهٔ منتشرشده</a> تغییر دهید و سپس Claude Desktop را دوباره راه‌اندازی کنید.</p>

<h3 id="codex" dir="rtl" align="right">Codex</h3>

<p dir="rtl" align="right">افزونهٔ <code dir="ltr">text-to-cad</code> را از <a href="https://chatgpt.com/plugins/plugins_6ac09476ef008191a35887b22b0d048a" dir="ltr">فهرست افزونه‌های Codex</a> نصب کنید، سپس گزینهٔ <strong dir="ltr">Open in desktop app</strong> (باز کردن در برنامهٔ دسکتاپ) را انتخاب کنید.</p>

<p dir="rtl" align="right">در برنامهٔ Codex، افزونه نمایشگر CAD را نیز اضافه می‌کند: بخش <strong dir="ltr">CAD</strong> در نوار کناری برای مدل‌های اخیر و باز کردن فایل‌ها، زبانهٔ <strong dir="ltr">CAD</strong> کنار هر گفت‌وگویی که عامل در آن کار می‌کند و گزینهٔ <em dir="ltr">Open with CAD</em> برای فایل‌های مدل.</p>

<details>
<summary dir="rtl" align="right">نصب دستی</summary>

```bash
codex plugin marketplace add earthtojake/text-to-cad --ref latest
codex plugin add text-to-cad@earthtojake
```

<p dir="rtl" align="right">برای به‌روزرسانی، بازارچهٔ <code dir="ltr">earthtojake</code> را ارتقا دهید (یا از مسیر <code dir="ltr">Plugins › Manage › Marketplace</code> استفاده کنید) و سپس Codex را دوباره راه‌اندازی کنید:</p>

```bash
codex plugin marketplace upgrade earthtojake
```

<p dir="rtl" align="right">برای نصب مجدد، افزونه و بازارچه را حذف کنید و سپس دستورهای نصب را دوباره اجرا کنید:</p>

```bash
codex plugin remove text-to-cad@earthtojake
codex plugin marketplace remove earthtojake
```

<p dir="rtl" align="right">نام بازارچه از <code dir="ltr">text-to-cad</code> به <code dir="ltr">earthtojake</code> تغییر کرده است. اگر قبلاً نام قدیمی را اضافه کرده‌اید، ابتدا آن را با دستور زیر حذف کنید:</p>

```bash
codex plugin marketplace remove text-to-cad
```

</details>

<h3 id="cursor" dir="rtl" align="right">Cursor</h3>

<p dir="rtl" align="right">Cursor افزونه‌ای را که با Claude Code نصب شده است نیز بارگذاری می‌کند. اگر افزونهٔ Claude Code را نصب کرده‌اید، <code dir="ltr">text-to-cad</code> از قبل در Cursor موجود است و نیازی به نصب دوباره ندارید.</p>

```bash
git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad
```

<p dir="rtl" align="right">Cursor فایل <code dir="ltr">.cursor-plugin/plugin.json</code> را می‌خواند؛ پس از کلون‌کردن مخزن، Cursor را دوباره راه‌اندازی کنید. تیم‌ها می‌توانند مخزن را از مسیر <code dir="ltr">Dashboard → Plugins &amp; MCPs → Team Marketplaces</code> نیز وارد کنند.</p>

<p dir="rtl" align="right">برای به‌روزرسانی، آخرین نسخه را دریافت کنید و سپس Cursor را دوباره راه‌اندازی کنید:</p>

```bash
git -C ~/.cursor/plugins/local/text-to-cad pull
```

<p dir="rtl" align="right">برای نصب مجدد، پوشه را حذف کنید و دستور نصب را دوباره اجرا کنید:</p>

```bash
rm -rf ~/.cursor/plugins/local/text-to-cad
```

<h3 id="grok-build" dir="rtl" align="right">Grok Build</h3>

<p dir="rtl" align="right">Grok Build نیز افزونهٔ نصب‌شده با Claude Code را بارگذاری می‌کند. اگر افزونهٔ Claude Code نصب شده باشد، <code dir="ltr">text-to-cad</code> در Grok Build هم در دسترس است و نصب جداگانه لازم نیست.</p>

```bash
grok plugin install earthtojake/text-to-cad@latest --trust
grok plugin enable text-to-cad
```

<p dir="rtl" align="right">Grok Build فایل معرفی افزونهٔ Claude را می‌خواند. از آنجا که Grok نتیجهٔ ابزارها را به‌صورت متن نشان می‌دهد، با درخواست نمایش مدل، پیوندی به نمایشگر CAD دریافت می‌کنید.</p>

<p dir="rtl" align="right">برای به‌روزرسانی، دستور زیر را اجرا کنید و سپس Grok Build را دوباره راه‌اندازی کنید:</p>

```bash
grok plugin update text-to-cad
```

<p dir="rtl" align="right">برای نصب مجدد، افزونه را با دستور زیر حذف و سپس دستورهای نصب را دوباره اجرا کنید:</p>

```bash
grok plugin uninstall text-to-cad
```

<h3 id="gemini" dir="rtl" align="right">Gemini</h3>

```bash
gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest --consent --auto-update
```

<p dir="rtl" align="right">Gemini افزونه را به‌شکل یک افزونهٔ توسعه‌ای نصب می‌کند؛ این نصب شامل مهارت‌ها و سرور CAD است و با گزینهٔ <code dir="ltr">--auto-update</code> به‌روز می‌ماند. گزینهٔ <code dir="ltr">--consent</code> نیز به پرسش امنیتی برنامه پاسخ مثبت می‌دهد. مانند Grok، نتیجهٔ ابزارها به‌صورت متن نمایش داده می‌شود؛ بنابراین با درخواست نمایش مدل، پیوند نمایشگر CAD دریافت می‌کنید.</p>

<p dir="rtl" align="right">برای به‌روزرسانی فوری، دستور زیر را اجرا کنید و سپس Gemini را دوباره راه‌اندازی کنید:</p>

```bash
gemini extensions update text-to-cad
```

<p dir="rtl" align="right">برای نصب مجدد، افزونه را با دستور زیر حذف و سپس دستور نصب را دوباره اجرا کنید:</p>

```bash
gemini extensions uninstall text-to-cad
```

<h3 id="other-agents" dir="rtl" align="right">سایر عامل‌ها</h3>

<p dir="rtl" align="right">اگر عامل شما از افزونه‌ها پشتیبانی نمی‌کند، مهارت‌ها ابزارهای لازم برای گردش‌کارهای اصلی CAD را فراهم می‌کنند و امکان مشاهدهٔ فایل‌های CAD را در یک برنامهٔ وب محلی نیز می‌دهند. برای نصب آن‌ها از ابزار خط فرمان Skills استفاده کنید:</p>

```bash
npx skills add earthtojake/text-to-cad#latest
```

<p dir="rtl" align="right">این دستور می‌پرسد مهارت‌ها برای کدام عامل و در چه مکانی نصب شوند. برای رد کردن پرسش‌ها، نام عامل را مشخص کنید و مهارت‌ها را برای حساب کاربری خود نصب کنید:</p>

```bash
npx skills add earthtojake/text-to-cad#latest -g -a <agent> -y
```

<p dir="rtl" align="right">هر مهارت، <code dir="ltr">cadgen</code> را از طریق <code dir="ltr">uv</code> و با همان دستور تثبیت‌شده‌ای اجرا می‌کند که سرور افزونه به کار می‌برد؛ بنابراین باید <code dir="ltr">uv</code> نصب باشد. بدون افزونه، سرور CAD وجود ندارد و مهارت‌ها مدل‌ها را در نمایشگر CAD مرورگر باز می‌کنند.</p>

<p dir="rtl" align="right"><strong>برای به‌روزرسانی یا نصب مجدد، همین دستور را دوباره اجرا کنید</strong> و سپس برنامه را راه‌اندازی مجدد کنید. دستور <code dir="ltr">add</code> بسته را دوباره دریافت می‌کند و نسخهٔ موجود را جایگزین می‌کند؛ در نتیجه، هم مهارت‌های فعلی را تازه‌سازی می‌کند و هم مهارت‌هایی را که در نسخهٔ جدید اضافه شده‌اند نصب می‌کند. دستور <code dir="ltr">npx skills update</code> فقط مهارت‌هایی را به‌روز می‌کند که از قبل در فایل قفل ثبت شده‌اند؛ بنابراین مهارت‌های جدید را بی‌سروصدا از قلم می‌اندازد. این موضوع مهم است، چون در نسخه‌های جدید مهارت‌های تازه‌ای اضافه می‌شوند.</p>

<p dir="rtl" align="right">هیچ‌یک از این دستورها مهارتی را که در نسخهٔ بالادستی منسوخ شده باشد حذف نمی‌کند؛ در صورت نیاز، با دستور <code dir="ltr">npx skills remove &lt;skill&gt;</code> آن را حذف کنید. مهارت منسوخ‌شدهٔ <code dir="ltr">cad-viewer</code> اکنون با مهارت‌های CAD، DXF و توضیحات ربات پوشش داده می‌شود و مهارت منسوخ‌شدهٔ <code dir="ltr">cad-mcp-setup</code> نیز با مراحل نصب و به‌روزرسانی همین README جایگزین شده است. برای حذف نصب‌های مستقل قدیمی، دستور زیر را اجرا کنید:</p>

```bash
npx skills remove cad-viewer cad-mcp-setup
```

<p dir="rtl" align="right">هنوز افزونه‌ای برای عامل شما وجود ندارد؟ <a href="https://github.com/earthtojake/text-to-cad/issues/new?title=Plugin%20request%3A%20" dir="ltr">درخواست ساخت افزونه ثبت کنید</a>.</p>

<h3 id="updates" dir="rtl" align="right">به‌روزرسانی‌ها</h3>

<p dir="rtl" align="right">برای به‌روزرسانی، از عامل خود بخواهید <code dir="ltr">text-to-cad</code> را به‌روز کند یا دستورهای به‌روزرسانی بخش مربوط به برنامه‌تان را اجرا کنید؛ سپس برنامه را دوباره راه‌اندازی کنید.</p>

<p dir="rtl" align="right">وقتی نسخهٔ جدیدی منتشر شود، نسخه‌ای که خودتان نصب کرده‌اید این موضوع را اعلام می‌کند: دکمه‌ای آبی برای به‌روزرسانی در نوار پیمایش CAD و صفحهٔ اصلی آن ظاهر می‌شود. گزینهٔ <strong dir="ltr">Send to agent</strong> پیام <code dir="ltr">Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad</code> را در گفت‌وگوی شما می‌فرستد؛ متن پیام شبیه پیام نصب است. در نمایشگر مرورگر، این پیام کپی می‌شود و در برنامه‌هایی که پاسخ CAD را به‌صورت متن نشان می‌دهند، خط پاسخ آن نمایش داده می‌شود. سپس عامل شما دستورهای به‌روزرسانی همین بخش را اجرا می‌کند. این دکمه به <a href="https://www.texttocad.dev/install" dir="ltr">دستورالعمل نصب</a> نیز پیوند دارد تا بتوانید دستی به‌روزرسانی کنید. نسخه‌هایی که از فهرست افزونه‌ها یا بازارچهٔ Cursor نصب شده‌اند این دکمه را نشان نمی‌دهند، چون فروشگاه مربوطه آن‌ها را به‌روز می‌کند. افزونهٔ Gemini نیز چنین دکمه‌ای ندارد، چون خود Gemini آن را به‌روزرسانی می‌کند؛ بنابراین برای این نسخه‌ها نیازی به اجرای دستور نیست.</p>

<p dir="rtl" align="right">برای بررسی انتشار نسخهٔ جدید، <code dir="ltr">cadgen</code> حداکثر روزی یک بار نشانی <code dir="ltr">api.texttocad.dev/v1/versions</code> را دریافت می‌کند. این کار تنها یک درخواست ناشناس است و هیچ شناسه، مسیر یا اطلاعات دیگری دربارهٔ شما ارسال نمی‌کند؛ در فرایند CI انجام نمی‌شود و برای نسخه‌ای که ابزار دیگری به‌روزرسانی‌اش می‌کند نیز اجرا نمی‌شود. برای خاموش کردن این بررسی، متغیر <code dir="ltr">CADGEN_UPDATE_CHECK=0</code> را تنظیم کنید.</p>

<h3 id="usage-analytics" dir="rtl" align="right">آمار استفاده</h3>

<p dir="rtl" align="right">برنامهٔ CAD (سرور <code dir="ltr">cad</code> افزونه) و نمایشگر مرورگر (<code dir="ltr">cadgen viewer</code>) می‌توانند آمار ناشناس استفاده را ارسال کنند؛ از جمله شناسهٔ تصادفی نصب، نسخه‌ها، محل دریافت برنامه، سیستم‌عامل و برنامهٔ عامل، تعداد دفعات استفاده از هر ابزار CAD و نماها، همچنین کدی یک‌طرفه و قالب هر فایل متمایزی که نمایش داده شده است (برای شمارش فایل‌ها، نه شناسایی آن‌ها). سرور ما همچنین تعداد نصب‌ها را بر اساس کشور و از روی نشانی IP هر درخواست محاسبه می‌کند، اما فقط مجموع هفتگی و ماهانه را نگه می‌دارد. نام فایل‌ها، مسیرها، محتوا یا متن درخواست‌های شما هرگز ارسال نمی‌شوند.</p>

<p dir="rtl" align="right">این قابلیت تا زمانی که در پرسش یک‌بارهٔ یکی از دو برنامه اجازه ندهید خاموش است؛ همان یک پاسخ برای هر دو برنامه اعمال می‌شود. بعداً می‌توانید از گزینهٔ <strong dir="ltr">Share anonymous usage data</strong> در منوی هر برنامه (لوگو در گوشهٔ بالا-چپ، هنگام نمایش هر مدل)، دستور <code dir="ltr">uvx cadgen analytics on|off</code> یا درخواست از عامل خود برای خاموش کردن آن استفاده کنید. تنظیم <code dir="ltr">DO_NOT_TRACK=1</code> آن را خاموش نگه می‌دارد. جزئیات بیشتر در <a href="https://www.texttocad.dev/privacy-policy">سیاست حفظ حریم خصوصی</a> آمده است.</p>

<h3 id="windows-11-smart-app-control" dir="rtl" align="right">Windows 11: قابلیت Smart App Control</h3>

<p dir="rtl" align="right">هستهٔ CAD که پشت مهارت‌های <code dir="ltr">cad</code>، <code dir="ltr">dxf</code>، <code dir="ltr">urdf</code>، <code dir="ltr">srdf</code> و <code dir="ltr">sdf</code> قرار دارد، <code dir="ltr">OCP</code> است؛ یعنی اتصال پایتونی OpenCascade. بستهٔ نصب آن شامل یک ماژول بومیِ بدون امضای دیجیتال است. قابلیت Smart App Control در Windows 11 کد بومیِ بدون امضا را مسدود می‌کند؛ بنابراین روی سیستمی که این قابلیت فعال باشد (که در نصب تازه به‌طور پیش‌فرض فعال است)، همهٔ دستورهای <code dir="ltr">cadgen</code> و دستور <code dir="ltr">import build123d</code> با خطای <code dir="ltr">ImportError: DLL load failed while importing OCP</code> شکست می‌خورند. در این حالت، Event Viewer رد شدن اجرا را با شناسهٔ رویداد 3077 در بخش <code dir="ltr">CodeIntegrity › Operational</code> ثبت می‌کند. دستور <code dir="ltr">cadgen doctor</code> نیز در صورت تشخیص این مشکل، به آن اشاره می‌کند.</p>

<p dir="rtl" align="right">برای Smart App Control امکان استثنا کردن یک برنامهٔ خاص وجود ندارد. یا آن را از مسیر <code dir="ltr">Settings › Privacy &amp; security › Windows Security › App &amp; browser control › Smart App Control settings</code> خاموش کنید (پس از خاموش شدن، فقط با نصب مجدد ویندوز می‌توان آن را دوباره روشن کرد)، یا مهارت‌های CAD را در محیط <code dir="ltr">WSL</code> اجرا کنید؛ این محدودیت در WSL اعمال نمی‌شود. بستهٔ نصب را پروژهٔ <code dir="ltr">cadquery-ocp</code> می‌سازد؛ بنابراین امضای دیجیتال آن در اختیار این مخزن نیست.</p>

<h2 id="skills" dir="rtl" align="right">🧰 مهارت‌ها (Skills)</h2>

<p dir="rtl" align="right">این کتابخانه را نصب کنید تا عامل‌های هوش مصنوعی بتوانند از گردش‌کارهای تخصصی CAD، ساخت و تولید، فایل‌های توصیف ربات، شبیه‌سازی و بازبینی محلی استفاده کنند.</p>

<table dir="rtl" align="right">
<thead>
<tr><th align="right">مهارت</th><th align="right">توضیحات</th><th align="right">منبع</th></tr>
</thead>
<tbody>
<tr><td dir="ltr">CAD</td><td align="right">ساخت و ویرایش مدل‌های CAD بر اساس توضیح متنی ساده یا تصویر؛ خروجی اصلی <code dir="ltr">STEP</code> است و امکان خروجی گرفتن با فرمت‌های <code dir="ltr">STL</code>، <code dir="ltr">3MF</code> و <code dir="ltr">GLB</code> نیز وجود دارد.</td><td dir="ltr"><a href="skills/cad/SKILL.md">skills/cad</a></td></tr>
<tr><td dir="ltr">step.parts</td><td align="right">یافتن قطعات آماده با فرمت STEP، مانند پیچ، یاتاقان، موتور و کانکتور.</td><td dir="ltr"><a href="skills/step-parts/SKILL.md">skills/step-parts</a></td></tr>
<tr><td dir="ltr">Engineering Drawing</td><td align="right">تولید نقشه‌های مهندسی اندازه‌گذاری‌شده از یک قطعه در قالب PDF، شامل نماها، خطوط پنهان، اندازه‌ها، علائم سوراخ‌ها و کادر مشخصات نقشه.</td><td dir="ltr"><a href="skills/engineering-drawing/SKILL.md">skills/engineering-drawing</a></td></tr>
<tr><td dir="ltr">DXF</td><td align="right">ساخت نقشه‌های دوبعدی DXF، مانند پروفیل‌ها، الگوها، واشرها و چیدمان برش، از کد پایتون یا هندسهٔ CAD.</td><td dir="ltr"><a href="skills/dxf/SKILL.md">skills/dxf</a></td></tr>
<tr><td dir="ltr">URDF</td><td align="right">نوشتن فایل‌های ساختار ربات شامل پیوندها، مفصل‌ها، محدودیت‌ها، مشخصات اینرسی و مش‌ها.</td><td dir="ltr"><a href="skills/urdf/SKILL.md">skills/urdf</a></td></tr>
<tr><td dir="ltr">SRDF</td><td align="right">افزودن گروه‌های برنامه‌ریزی MoveIt، ابزارهای انتهایی، وضعیت‌ها و قوانین برخورد به فایل URDF.</td><td dir="ltr"><a href="skills/srdf/SKILL.md">skills/srdf</a></td></tr>
<tr><td dir="ltr">SDF</td><td align="right">ساخت مدل‌ها و محیط‌های شبیه‌سازی همراه با چارچوب‌های مختصات، فیزیک، حسگرها و نورها.</td><td dir="ltr"><a href="skills/sdf/SKILL.md">skills/sdf</a></td></tr>
<tr><td dir="ltr">SendCutSend</td><td align="right">بررسی فایل‌های DXF و STEP پیش از بارگذاری در سرویس SendCutSend.</td><td dir="ltr"><a href="skills/sendcutsend/SKILL.md">skills/sendcutsend</a></td></tr>
<tr><td dir="ltr">DfAM Check</td><td align="right">سنجش مناسب‌بودن مش برای چاپ سه‌بعدی بر اساس فرایند؛ شامل ضخامت دیواره، برآمدگی‌ها، حجم تکیه‌گاه و جهت‌گیری هنگام ساخت.</td><td dir="ltr"><a href="skills/dfam-check/SKILL.md">skills/dfam-check</a></td></tr>
<tr><td dir="ltr">DFM</td><td align="right">بررسی قطعه برای تولید با ورق فلزی، ماشین‌کاری CNC یا قالب‌گیری تزریقی؛ همراه با شواهد اندازه‌گیری‌شده و ارجاع به قاعدهٔ مربوط برای هر یافته. همچنین شیب قالب، زیر‌بُرها و سطح تصویرشده را از روی مش اندازه‌گیری می‌کند.</td><td dir="ltr"><a href="skills/dfm/SKILL.md">skills/dfm</a></td></tr>
<tr><td dir="ltr">G-code</td><td align="right">برش لایه‌ای مدل‌ها با OrcaSlicer و تولید G-code آمادهٔ چاپ، با استفاده از تنظیمات اختصاصی چاپگر شما.</td><td dir="ltr"><a href="skills/gcode/SKILL.md">skills/gcode</a></td></tr>
<tr><td dir="ltr">Bambu Labs</td><td align="right">ارسال کارهای چاپ به چاپگرهای Bambu Lab از طریق Bambu Connect، برنامهٔ رسمی Bambu Lab یا Bambu Studio.</td><td dir="ltr"><a href="skills/bambu-labs/SKILL.md">skills/bambu-labs</a></td></tr>
</tbody>
</table>

<h2 id="contributing" dir="rtl" align="right">🛠️ مشارکت در پروژه</h2>

<p dir="rtl" align="right">شاخه‌ای از <code dir="ltr">main</code> ایجاد کنید و درخواست ادغام (PR) را به شاخهٔ <code dir="ltr">main</code> بفرستید. برای آشنایی با روند کار محلی، آزمایش در برنامه‌های عامل و اعتبارسنجی، فایل <a href="CONTRIBUTING.md" dir="ltr">CONTRIBUTING.md</a> را ببینید.</p>
