# Terminal Menu Navigator — متصفح قوائم الطرفية

An NVDA add-on that makes interactive CLI menus in terminals usable with speech.

إضافة لقارئ الشاشة NVDA تجعل القوائم التفاعلية في الطرفيات قابلة للاستخدام بالكلام.

---

## العربية

### المشكلة
عندما تعرض أدوات سطر الأوامر الحديثة (معالجات npm، أدوات inquirer وclack، قوائم Claude Code) خيارات تتنقل بينها بالسهمين، فإنها تعيد رسم القائمة كاملة مع كل ضغطة عبر رموز ANSI. قارئ الشاشة يرى "نصاً تغيّر" فيعيد قراءة كل الخيارات — أو أجزاء عشوائية منها — فلا تعرف أبداً في أي خيار أنت.

### الحل
تعتمد الإضافة مبدأ **"اقرأ الحالة لا الحدث"**: إعلانات النص الجديد تُستخدم كمشغّل فقط، وعند استقرار إعادة الرسم (مهلة 60 مللي ثانية) تقرأ الإضافة مخزن الطرفية الفعلي وتحدد القائمة فيه، ثم تنطق **الخيار المحدد فقط مع موضعه**: "cherry، 3 من 5". عند ظهور قائمة جديدة يُنطق سطر السؤال مرة واحدة.

تدعم عائلتين من القوائم:
- **قوائم المؤشر** (inquirer وأخواتها): `> خيار` أو `❯ خيار`
- **قوائم الدوائر** (clack، مثل create-vite): `● خيار` محدد بين `○` مع حدود صناديق `│`

### الاختصارات (قابلة لإعادة التعيين)
- **NVDA+Alt+L**: تشغيل/إيقاف الفلترة فوراً (صمام الأمان)
- **NVDA+Alt+K**: إعادة نطق الخيار المحدد وموضعه والسؤال عند الطلب

### التثبيت
ثبّت ملف `TerminalMenuNav.nvda-addon` بفتحه من مستكشف الملفات، أو ابنه بنفسك:
```
powershell -ExecutionPolicy Bypass -File build.ps1
```

### النطاق والأمان
تعمل في الكونسول الكلاسيكي وWindows Terminal وطرفية VS Code المدمجة. التصميم "يفشل بأمان": أي كلام لا يخص قائمة نشطة يمر دون تغيير، وأي نص ابتُلع بالخطأ يُعاد نطقه إن لم توجد قائمة، وأي خطأ داخلي يعيد الكلام الأصلي كما هو.

### قيود معروفة
- في القوائم ذات النافذة المتمررة (مثل vite) يكون الموضع المعلن ضمن الخيارات المرئية فقط.
- حقول إدخال النص في clack (مثل "Project name") خارج نطاق الإضافة حالياً.
- برايل غير مفلتر (الفلترة كلام فقط).

---

## English

### The problem
Modern CLI tools (npm wizards, inquirer- and clack-style prompts, Claude Code menus) repaint their whole option list on every arrow press using ANSI escapes. A screen reader sees "text changed" and re-reads all the options — or random fragments — so you never know which option you are on.

### The solution
The add-on follows a **"read the state, not the event"** principle: new-text announcements are only a trigger. Once the repaint settles (a 60 ms debounce), the add-on reads the actual terminal buffer, locates the menu there, and announces **only the pointed option and its position**: "cherry, 3 of 5". When a new menu appears, its question line is announced once.

Two menu families are supported:
- **Pointer menus** (inquirer family): `> option` / `❯ option`
- **Radio menus** (clack family, e.g. create-vite): one filled `●` among `○`, behind `│` box borders

### Gestures (remappable)
- **NVDA+Alt+L**: toggle the filtering instantly (your safety valve)
- **NVDA+Alt+K**: repeat the selected option, its position, and the question on demand

### Installation
Install `TerminalMenuNav.nvda-addon` by opening it from File Explorer, or build it yourself:
```
powershell -ExecutionPolicy Bypass -File build.ps1
```

### Scope and safety
Works in classic consoles, Windows Terminal, and the VS Code integrated terminal. The design fails open: speech unrelated to an active menu passes through untouched, anything swallowed by mistake is re-spoken when no menu is found, and any internal error returns the original speech unchanged.

### Known limitations
- In scrolling-viewport menus (like vite's) the announced position is within the visible options only.
- clack text-input fields (like "Project name") are out of scope for now.
- Braille is not filtered (speech only).

### Development
The detection core (`menuDetect.py`) is pure Python with no NVDA dependency. Every defect found in live NVDA speech logs is reproduced as a test case before it is fixed:
```
python tests/test_menu_detect.py
python tests/test_plugin_sim.py
```
See `DEV_NOTES.md` (Arabic) for the full engineering log.

## License / الرخصة
[GPL v2](LICENSE) — the standard license of the NVDA add-on community.

## Author / المؤلف
Islam Benmebarek <islam.benmebarek.dz@gmail.com>
