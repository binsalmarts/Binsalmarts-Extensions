import AppKit
import Foundation

// Native text drawing keeps Arabic letters joined and the writing direction correct.
let here = URL(fileURLWithPath: CommandLine.arguments[1])
let out = here.appendingPathComponent("screens")
try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
let W = 1920, H = 1080
func color(_ value: String, _ alpha: CGFloat = 1) -> NSColor {
    let v = UInt32(value, radix: 16)!
    return NSColor(red: CGFloat((v >> 16) & 255)/255, green: CGFloat((v >> 8) & 255)/255,
                   blue: CGFloat(v & 255)/255, alpha: alpha)
}
let orange = color("d49061"), white = color("f4f6fa"), gray = color("b4bdce"), mint = color("5edbc0")
let icon = NSImage(contentsOf: here.appendingPathComponent("assets/icon.png"))!
let name = NSImage(contentsOf: here.appendingPathComponent("assets/name.png"))!
func rect(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ fill: NSColor, _ r: CGFloat = 16, stroke: NSColor? = nil, line: CGFloat = 2) {
    let p = NSBezierPath(roundedRect: NSRect(x:x,y:y,width:w,height:h), xRadius:r, yRadius:r)
    fill.setFill(); p.fill()
    if let s = stroke {s.setStroke(); p.lineWidth = line; p.stroke()}
}
func txt(_ s: String, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ size: CGFloat = 32,
         _ c: NSColor = white, arabic: Bool = false, bold: Bool = false, center: Bool = false) {
    let p = NSMutableParagraphStyle()
    p.alignment = center ? .center : (arabic ? .right : .left)
    p.baseWritingDirection = arabic ? .rightToLeft : .leftToRight
    p.lineSpacing = 8
    let font = NSFont.systemFont(ofSize:size, weight:bold ? .semibold : .regular)
    NSAttributedString(string:s, attributes:[.font:font, .foregroundColor:c, .paragraphStyle:p])
        .draw(in:NSRect(x:x,y:y,width:w,height:h))
}
func image(_ im: NSImage, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, alpha: CGFloat = 1) {
    im.draw(in:NSRect(x:x,y:y,width:w,height:h), from:.zero, operation:.sourceOver,
            fraction:alpha, respectFlipped:true, hints:[.interpolation:NSImageInterpolation.high])
}
func logoH(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat) {
    image(name,x,y + w*0.012,w*0.68,w*0.68*522/1622)
    image(icon,x+w*0.75,y,w*0.25,w*0.25*650/744)
}
func logoV(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat) {
    image(icon,x+w*0.25,y,w*0.5,w*0.5*650/744)
    image(name,x,y+w*0.62,w,w*522/1622)
}
func exported(_ type: String, _ version: String, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) {
    let path = here.appendingPathComponent("output/النخاله-logo-kit/\(type)/\(version)/النخاله-\(type)-\(version)-512px.png")
    guard let im = NSImage(contentsOf:path) else {return}
    let ratio = min(w/im.size.width,h/im.size.height)
    let iw = im.size.width*ratio, ih = im.size.height*ratio
    image(im,x+(w-iw)/2,y+(h-ih)/2,iw,ih)
}
func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) {
    let p = NSBezierPath(rect:NSRect(x:x,y:y,width:w,height:h))
    mint.setStroke(); p.lineWidth = 3; p.setLineDash([8,6],count:2,phase:0); p.stroke()
    for (a,b) in [(x,y),(x+w,y),(x,y+h),(x+w,y+h)] {
        rect(a-5,b-5,10,10,color("0b1321"),2,stroke:mint,line:2)
    }
}
func pill(_ s: String, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat, accent: NSColor = mint) {
    rect(x,y,w,50,accent.withAlphaComponent(0.1),16,stroke:accent.withAlphaComponent(0.4))
    txt(s,x+15,y+9,w-30,40,24,accent,center:true)
}
func side(_ heading: String, _ body: String, _ note: String = "") {
    rect(1320,310,500,565,color("152034"),24)
    txt(heading,1354,345,430,125,43,white,arabic:true,bold:true)
    txt(body,1354,475,430,250,34,gray,arabic:true)
    if !note.isEmpty {
        rect(1348,744,444,104,orange.withAlphaComponent(0.10),14)
        txt(note,1367,759,406,89,29,orange,arabic:true)
    }
}
func chrome(_ tab: String) {
    rect(100,300,1150,580,color("1d2431"),23,stroke:color("394255"))
    rect(100,300,1150,65,color("252e3c"),23)
    txt("Logo Export Pro · 1.2",130,316,1000,45,29,white,bold:true)
    let tabs = ["Source","Layouts","Sizing","Colors","Export"]
    for (i,t) in tabs.enumerated() {
        let x = CGFloat(130+i*182)
        if t == tab {rect(x,388,162,49,orange.withAlphaComponent(0.15),10,stroke:orange)}
        txt(t,x+12,396,140,38,26,t == tab ? orange : gray,center:true)
    }
}
func field(_ label: String, _ value: String, _ y: CGFloat, highlight: Bool = false, arabic: Bool = false) {
    txt(label,143,y+11,330,55,28,gray)
    rect(470,y,737,65,color("2c3544"),10,stroke:highlight ? mint : color("465064"))
    txt(value,490,y+13,690,52,27,white,arabic:arabic)
}
func check(_ s: String, _ x: CGFloat, _ y: CGFloat, _ checked: Bool = true, _ highlight: Bool = false) {
    rect(x,y+4,28,28,checked ? mint : color("293243"),5,stroke:highlight ? orange : gray)
    if checked {txt("✓",x+2,y-1,29,38,27,color("0b1321"),bold:true)}
    txt(s,x+43,y,960-x+143,50,28,white)
}
struct Scene {
    let title: String
    let subtitle: String
    let footer: String
    let duration: Double
    let draw: () -> Void
    let highlight: [Double]
}
var scenes: [Scene] = []
func add(_ title: String, _ sub: String, _ foot: String, _ d: Double, _ h: [Double] = [], _ body: @escaping () -> Void) {
    scenes.append(Scene(title:title,subtitle:sub,footer:foot,duration:d,draw:body,highlight:h))
}
add("من تصميم الشعار إلى حزمة تسليم", "شرح إضافة Logo Export Pro في Inkscape", "عناوين وخطوات عربية • دون صوت", 6) {
    rect(240,312,1440,540,color("162136"),30)
    image(icon,817,348,286,250)
    image(name,625,632,670,216)
}
add("جهّز النسخ كما تريدها", "احتفظ بمقاسات العناصر وتباعدها وترتيبها الحالي", "الاسم يمكن أن يكون نصًا أو مسارات أو صورة؛ لا يلزم أن يكون Text.", 9) {
    rect(100,310,1150,565,color("182237"),24)
    logoH(145,385,545); logoV(822,352,320); image(icon,530,650,150,131)
    pill("Horizontal",225,540,340); pill("Vertical",820,685,320); pill("Icon",505,800,200)
    side("ثلاث نسخ جاهزة", "نسخة أفقية\nنسخة عمودية\nأيقونة مستقلة", "استخدم نفس الأيقونة في النسخ.")
}
add("اجمع عناصر كل نسخة وحدها", "من قائمة Object اختر Group لكل تصميم مكتمل", "لا تجمع الأفقي والعمودي والأيقونة داخل مجموعة واحدة.", 9,[145,385,545,150]) {
    rect(100,310,1150,565,color("182237"),24)
    logoH(145,385,545); logoV(822,352,320); image(icon,530,650,150,131)
    box(134,369,570,152); box(810,340,343,336); box(518,638,174,154)
    side("مجموعة لكل نسخة", "حدّد الأيقونة والاسم في النسخة الأفقية، ثم Group.\nكرر ذلك للنسخة العمودية.", "الأيقونة المستقلة قد تكون عنصرًا أو مجموعة.")
}
add("حدّد النسخ الثلاث معًا", "استخدم Shift مع النقر على كل مجموعة", "يمكن للإضافة استخراج الاسم من النسخ المركّبة؛ لا تحتاج إلى نسخة اسم مستقلة.", 8,[134,340,1020,451]) {
    rect(100,310,1150,565,color("182237"),24)
    logoH(145,385,545); logoV(822,352,320); image(icon,530,650,150,131)
    box(134,369,570,152); box(810,340,343,336); box(518,638,174,154)
    side("جاهزة للتعرف", "التطابق بين الأيقونات يساعد الإضافة على معرفة الأجزاء المتكررة واستخراجها مرة واحدة.")
}
add("افتح الإضافة", "اتبع المسار داخل قائمة Extensions", "Extensions → Binsalmarts Extensions > → Logo Export Pro", 7,[190,641,990,100]) {
    rect(100,310,1150,565,color("182237"),24)
    let entries = ["Extensions","Binsalmarts Extensions >","Logo Export Pro"]
    for (i,s) in entries.enumerated() {
        let y = CGFloat(367+i*137)
        rect(190,y,990,100,color("2a3446"),17,stroke:i == 2 ? mint : color("475267"))
        txt(s,225,y+26,930,68,35,i == 2 ? mint : white,bold:i == 2)
    }
    side("القائمة الموحّدة", "اختر Logo Export Pro لفتح إعدادات تصدير حزمة الشعار.")
}
add("اختر Ready variants", "في تبويب Source اختر وضع التصاميم الجاهزة", "Brand / folder name يغيّر اسم الملفات فقط؛ تصميم الاسم يبقى كما هو.", 10,[463,558,750,78]) {
    chrome("Source")
    field("Action","Export logo kit",475)
    field("Logo source","Ready variants · detect selected designs",565,highlight:true)
    field("Brand / folder name","النخاله",655,arabic:true)
    check("Convert exported text to paths",145,765)
    side("التصميم الحالي", "يحفظ الأفقي والعمودي كما صممتهما، ثم يستخرج الأيقونة والاسم مرة واحدة.", "اترك Action على Export logo kit.")
}
add("اختر الأشكال المطلوبة", "من تبويب Layouts فعّل النسخ التي تريد إخراجها", "في Ready variants تُحفظ التصاميم الجاهزة؛ إعدادات إعادة بناء الحجم والتباعد لا تغيّرها.", 8,[137,478,1060,178]) {
    chrome("Layouts")
    check("Horizontal",145,490); check("Vertical",690,490)
    check("Icon only",145,575); check("Name only",690,575)
    check("Square icon-only canvas",145,711)
    txt("Each detected type is exported once.",145,789,1020,60,29,gray)
    side("أربع نتائج", "أفقي\nعمودي\nأيقونة فقط\nاسم فقط", "Square icon يضيف مساحة مربعة حول الأيقونة.")
}
add("اختر النسخ اللونية", "من تبويب Colors فعّل Original وBlack وWhite", "لهذا المثال: ألغِ White details become cutouts لأن الاسم الأبيض جزء ظاهر من الشعار.", 11,[136,572,1070,77]) {
    chrome("Colors")
    check("Original colors",145,486); check("Black",570,486); check("White",900,486)
    check("White details become cutouts",145,590,false,true)
    check("Transparent export background",145,687)
    rect(148,768,59,49,color("6b7280"),8); txt("Light background: #6b7280",230,774,800,60,28,gray)
    side("احتفظ بالاسم الأبيض", "إلغاء Cutouts يمنع التعامل مع الاسم الأبيض كفراغ شفاف في النسخ أحادية اللون.", "PNG وSVG وPDF تدعم الخلفية الشفافة.")
}
add("اجعل الاسم الأبيض ظاهرًا", "JPG وEPS يستخدمان خلفية مصمتة", "في هذا المثال اختر خلفية رمادية في Light background لتظهر الألوان الأصلية والأسود.", 8,[138,540,1045,162]) {
    chrome("Colors")
    txt("Solid backgrounds for JPG / EPS",145,482,1030,60,32,white,bold:true)
    rect(145,548,1030,148,color("6b7280"),14)
    logoH(389,563,535)
    rect(145,720,1030,96,color("172033"),14)
    txt("White version background: #172033",175,746,980,60,31,white)
    side("خلفية مناسبة", "الاسم الأصلي أبيض، ولذلك يختفي على خلفية بيضاء.\nالخلفية الرمادية تظهره وتُبقي النسخة السوداء واضحة.")
}
add("حدد المجلد والصيغ والمقاسات", "من تبويب Export اختر مكان حفظ الحزمة", "المقاسات هي طول الضلع الأكبر بالبكسل، مع الحفاظ على نسبة أبعاد التصميم.", 11,[136,625,1080,135]) {
    chrome("Export")
    field("Output folder","Choose your export folder…",469)
    check("SVG",145,568); check("PDF",410,568); check("EPS",675,568)
    check("PNG",145,625); check("JPG",410,625)
    field("PNG / JPG sizes (px)","512, 1024, 2048",690,highlight:true)
    check("Include HTML gallery and SVG previews",145,787)
    side("خمس صيغ", "SVG • PDF • EPS\nPNG • JPG\n\nاكتب المقاسات مفصولة بفاصلة.", "وجود صورة داخل SVG لا يحوّلها إلى مسارات.")
}
add("اضغط Apply للتصدير", "تُنشأ حزمة جديدة باسم الشعار داخل مجلد الإخراج", "يمكنك تعديل ترتيب الشعار ثم إعادة تشغيل الإضافة؛ ستقرأ التصميم الحالي من جديد.", 7,[685,656,430,100]) {
    rect(100,310,1150,565,color("182237"),24)
    txt("Ready to export",185,360,970,70,42,white,bold:true)
    txt("Ready variants",185,466,970,60,37,mint)
    txt("4 layouts × 3 colors × selected formats",185,547,1000,65,32,gray)
    rect(694,665,405,86,mint,18)
    txt("Apply",694,683,405,68,41,color("0b1321"),bold:true,center:true)
    side("انتظر اكتمال التصدير", "تختلف مدة التصدير حسب عدد الصيغ والمقاسات وتعقيد الشعار.", "ملف التصميم الأصلي يبقى كما هو.")
}
add("النتيجة: نسخ منظمة بلا تكرار", "أفقي وعمودي وأيقونة واسم؛ لكل نوع نسخه اللونية وصيغه", "افتح preview.html لمراجعة الحزمة. الإعدادات الموضحة تنتج 108 ملفات تصدير.", 10) {
    let types = ["horizontal","vertical","icon","wordmark"]
    for (i,s) in types.enumerated() {
        let x = CGFloat(100+i*437)
        rect(x,315,407,546,color("182237"),20,stroke:color("394a63"))
        txt(s,x+21,342,365,60,29,mint,bold:true,center:true)
        exported(s,"original",x+22,420,363,241)
        rect(x+18,684,177,90,color("c9ced8"),10)
        rect(x+212,684,177,90,color("0c1525"),10,stroke:color("394a63"))
        exported(s,"black",x+25,691,163,76)
        exported(s,"white",x+219,691,163,76)
        txt("Black",x+18,780,177,38,22,gray,center:true)
        txt("White",x+212,780,177,38,22,gray,center:true)
        txt("SVG  PDF  EPS  PNG  JPG",x+15,817,377,37,21,white,center:true)
    }
}
add("إذا التبس التعرف، عيّن النوع", "حدّد مجموعة واحدة واستخدم Action ثم Apply", "بعد التعيين حدّد النسخ كلها، وأعد Action إلى Export logo kit ووضع Ready variants.", 12,[137,477,1070,174]) {
    chrome("Source")
    field("Action","Assign selected group as Horizontal",474,highlight:true)
    rect(470,547,737,181,color("2c3544"),10,stroke:color("465064"))
    txt("Assign selected group as Vertical",490,569,690,46,27,white)
    txt("Assign selected object as icon",490,622,690,46,27,white)
    txt("Assign selected object as name",490,675,690,46,27,white)
    txt("Choose one action at a time, then Apply.",146,751,1000,50,29,gray)
    txt("Return to Export logo kit when finished.",146,808,1000,50,27,mint)
    side("أنت تحدد المعنى", "عيّن الأفقي والعمودي كلًا على حدة.\nيمكن أيضًا تعيين الأيقونة والاسم عند الحاجة.", "لا تحتاج إلى تسمية الطبقات.")
}
add("حزمة شعار جاهزة للتسليم", "ابدأ بالتصميم، ودع الإضافة تنظّم التصدير", "Logo Export Pro · 1.2  |  Inkscape", 6) {
    rect(240,310,1440,570,color("162136"),30)
    image(icon,821,347,278,243)
    image(name,625,628,670,216)
}

var metadata: [[String:Any]] = []
for (i,s) in scenes.enumerated() {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:W,pixelsHigh:H,bitsPerSample:8,
        samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:W*4,bitsPerPixel:32)!
    let context = NSGraphicsContext(bitmapImageRep:bitmap)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.cgContext.translateBy(x:0,y:CGFloat(H)); context.cgContext.scaleBy(x:1,y:-1)
    NSGraphicsContext.current = NSGraphicsContext(cgContext:context.cgContext,flipped:true)
    let gradient = NSGradient(starting:color("0a101c"),ending:color("111d31"))!
    gradient.draw(in:NSRect(x:0,y:0,width:W,height:H),angle:90)
    image(icon,70,44,45,39)
    txt("Logo Export Pro",134,44,800,55,30,white,bold:true)
    txt("شرح الاستخدام",1390,44,365,55,30,gray,arabic:true)
    pill(String(format:"%02d / %02d",i+1,scenes.count),1770,40,110,accent:orange)
    txt(s.title,100,125,1720,90,59,white,arabic:true,bold:true)
    txt(s.subtitle,100,223,1720,62,33,gray,arabic:true)
    s.draw()
    rect(100,924,1720,93,color("1c2a40"),17)
    txt(s.footer,124,946,1672,77,31,white,arabic:true,center:true)
    NSGraphicsContext.restoreGraphicsState()
    let file = String(format:"scene-%02d.png",i+1)
    try bitmap.representation(using:.png,properties:[:])!.write(to:out.appendingPathComponent(file))
    metadata.append(["image":file,"title":s.title,"duration":s.duration,"highlight":s.highlight])
}
try JSONSerialization.data(withJSONObject:metadata,options:[.prettyPrinted,.sortedKeys])
    .write(to:out.appendingPathComponent("scenes.json"))
print("Rendered \(scenes.count) Arabic tutorial scenes.")
