// cloudfunctions/analyzeMeal/index.js
const cloud = require('wx-server-sdk')
const https  = require('https')

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })

// ── 配置 ──────────────────────────────────────────────────
const ZHIPU_KEY      = process.env.ZHIPU_API_KEY
const ZHIPU_ENDPOINT = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'



// ── 封装 HTTPS POST ────────────────────────────────────────
function httpsPost(url, extraHeaders, bodyStr) {
  return new Promise((resolve, reject) => {
    const u = new URL(url)
    const options = {
      hostname: u.hostname,
      path:     u.pathname,
      method:   'POST',
      headers: {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(bodyStr),
        ...extraHeaders,
      },
    }
    const req = https.request(options, (res) => {
      let raw = ''
      res.on('data',  chunk => { raw += chunk })
      res.on('end',   () => {
        try   { resolve(JSON.parse(raw)) }
        catch { reject(new Error('JSON parse fail: ' + raw.slice(0, 300))) }
      })
    })
    req.on('error', reject)
    req.write(bodyStr)
    req.end()
  })
}

// ── 从 AI 返回文本中提取营养 JSON（鲁棒版）──────────────────
function parseNutrition(content) {
  if (!content) return null

  // 步骤 1：去除 markdown 代码块（```json ... ``` 或 ``` ... ```）
  let cleaned = content
    .replace(/```(?:json)?/gi, '')
    .replace(/```/g, '')
    .trim()

  // 步骤 2：提取最外层 {...}（允许嵌套，用栈匹配）
  let start = -1, depth = 0, jsonStr = null
  for (let i = 0; i < cleaned.length; i++) {
    if (cleaned[i] === '{') {
      if (depth === 0) start = i
      depth++
    } else if (cleaned[i] === '}') {
      depth--
      if (depth === 0 && start !== -1) {
        jsonStr = cleaned.slice(start, i + 1)
        break
      }
    }
  }
  if (!jsonStr) return null

  try {
    const obj = JSON.parse(jsonStr)

    // 兼容两种字段名：dishes（旧）/ components（新）/ calorieBreakdown
    const rawList = Array.isArray(obj.dishes)            ? obj.dishes
                  : Array.isArray(obj.components)        ? obj.components
                  : Array.isArray(obj.calorieBreakdown)  ? obj.calorieBreakdown
                  : []

    const dishes = rawList.slice(0, 10).map(d => {
      const item = { name: String((d && d.name) || '').slice(0, 20), calories: Math.round(Number(d && d.calories) || 0) }
      if (d && d.type) item.type = String(d.type).slice(0, 16)
      if (d && d.note) item.note = String(d.note).slice(0, 30)
      return item
    }).filter(d => d.name)

    return {
      name:     String(obj.name     || '未知食物').slice(0, 30),
      calories: Math.round(Number(obj.calories) || 0),
      protein:  Math.round(Number(obj.protein)  || 0),
      carbs:    Math.round(Number(obj.carbs)     || 0),
      fat:      Math.round(Number(obj.fat)       || 0),
      dishes,
    }
  } catch {
    return null
  }
}

// ── 兜底拆分：当 AI 仅返回 1 项且与总名称几乎一致时，按常见品类做组件级细分 ──
// 仅覆盖少量高频品类，避免规则爆炸。所有比例之和约等于 1，最后对总热量做补差。
const FALLBACK_CATEGORIES = [
  {
    name: '汉堡',
    keywords: [/汉堡/, /burger/i, /堡包/, /巨无霸/, /麦香/, /皇堡/],
    components: [
      { name: '面包',     type: 'bread',     ratio: 0.26 },
      { name: '肉饼',     type: 'patty',     ratio: 0.40 },
      { name: '芝士',     type: 'cheese',    ratio: 0.10 },
      { name: '生菜番茄', type: 'vegetable', ratio: 0.04 },
      { name: '酱料',     type: 'sauce',     ratio: 0.20 },
    ],
  },
  {
    name: '炸鸡/鸡腿',
    keywords: [/炸鸡/, /鸡腿/, /鸡翅/, /鸡块/, /鸡排/, /烤鸡/, /蜜汁鸡/, /照烧鸡/, /chicken/i],
    components: [
      { name: '鸡肉',       type: 'meat',  ratio: 0.72 },
      { name: '腌料/酱汁',  type: 'sauce', ratio: 0.18 },
      { name: '煎制/裹粉油', type: 'oil',   ratio: 0.10 },
    ],
  },
  {
    name: '三明治',
    keywords: [/三明治/, /sandwich/i, /帕尼尼/, /贝果/],
    components: [
      { name: '面包',   type: 'bread',     ratio: 0.40 },
      { name: '夹料',   type: 'filling',   ratio: 0.45 },
      { name: '蔬菜',   type: 'vegetable', ratio: 0.05 },
      { name: '酱料',   type: 'sauce',     ratio: 0.10 },
    ],
  },
  {
    name: '奶茶',
    keywords: [/奶茶/, /milk tea/i, /bubble tea/i, /珍珠/, /波霸/],
    components: [
      { name: '茶底+奶', type: 'base',      ratio: 0.45 },
      { name: '糖浆',   type: 'sugar',     ratio: 0.35 },
      { name: '小料',   type: 'topping',   ratio: 0.20 },
    ],
  },
]

// 名称归一：去空白/标点/常见后缀，便于"明细名 ≈ 餐食名"判断
function normalizeName(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[\s·•\-—_/\\()（）「」【】\[\]、，。.,!！?？]/g, '')
}

// 判断 dishes 是否需要兜底拆分：空，或只有 1 项且与餐食名几乎一致
function shouldFallback(name, dishes) {
  if (!Array.isArray(dishes) || dishes.length === 0) return true
  if (dishes.length === 1) {
    const a = normalizeName(name)
    const b = normalizeName(dishes[0].name)
    if (!a || !b) return true
    return a === b || a.includes(b) || b.includes(a)
  }
  return false
}

function matchCategory(name) {
  for (const cat of FALLBACK_CATEGORIES) {
    if (cat.keywords.some(re => re.test(name))) return cat
  }
  return null
}

// 把 components 按比例展开为 [{name, type, calories}]，并把舍入差吃到最后一项（优先酱料类）
function expandComponents(totalCal, components) {
  const items = components.map(c => ({
    name:     c.name,
    type:     c.type,
    calories: Math.round(totalCal * c.ratio),
  }))
  const sum  = items.reduce((s, x) => s + x.calories, 0)
  const diff = totalCal - sum
  if (diff !== 0 && items.length) {
    // 优先把差值加到 sauce/sugar/oil/seasoning 类，否则给最后一项
    const idx = items.findIndex(x => ['sauce', 'sugar', 'oil', 'seasoning'].includes(x.type))
    const target = idx >= 0 ? idx : items.length - 1
    items[target].calories = Math.max(0, items[target].calories + diff)
  }
  return items
}

// 入口：必要时用品类规则把单项明细二次拆分
function refineBreakdown(nutrition) {
  if (!nutrition) return nutrition
  const { name, calories, dishes } = nutrition
  if (!calories || calories <= 0) return nutrition
  if (!shouldFallback(name, dishes)) return nutrition

  const cat = matchCategory(name)
  if (!cat) return nutrition

  const expanded = expandComponents(calories, cat.components)
  return { ...nutrition, dishes: expanded }
}

// ── 延迟工具 ──────────────────────────────────────────────
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// ── 图片模式：单次识别 ─────────────────────────────────────
async function callZhipu(base64, hint) {
  const body = JSON.stringify({
    model: 'glm-4.6v-flash',
    messages: [
      {
        role: 'user',
        content: [
          {
            type:      'image_url',
            image_url: { url: `data:image/jpeg;base64,${base64}` },
          },
          {
            type: 'text',
            text:
              `请识别图中食物，估算1人份营养成分，并将卡路里拆解到"组成部分/配料"级别。` +
              (hint ? `用户补充说明：「${hint}」，若与图片不冲突则优先结合说明估算。` : '') +
              `\n【dishes 字段规则 - 非常重要】` +
              `\n1. dishes 必须返回"组成部分级别"的明细，不是整道菜级别。` +
              `\n2. 对组合食物（汉堡/三明治/便当/盖饭/沙拉/意面/奶茶等），必须拆成各个组成部分。` +
              `\n   - 汉堡 → 面包、肉饼、芝士、培根、生菜番茄、酱料` +
              `\n   - 三明治 → 面包、夹料、蔬菜、酱料` +
              `\n   - 便当/盖饭 → 主食(米饭)、主菜、配菜、酱汁` +
              `\n   - 沙拉 → 蔬菜、蛋白质(鸡胸/虾/蛋)、坚果/果干、沙拉酱` +
              `\n   - 奶茶 → 茶底+奶、糖浆、珍珠/小料` +
              `\n3. 对单品类但有调味的食物（蜜汁鸡腿、炸鸡、卤味、烤肉、煎牛排等），拆成 主食材 + 调料/酱汁/裹粉/用油。` +
              `\n   - 蜜汁鸡腿 → 鸡腿、蜜汁酱料、煎制用油` +
              `\n   - 炸鸡 → 鸡肉、裹粉、煎炸用油、调味料` +
              `\n4. 图中有多道菜时：先按每道菜列出，再尽量在每道菜内部细分（dishes 最多 10 项，超过则合并次要项）。` +
              `\n5. dishes 至少 3 项；只有真正单一无配料的食物（如一根香蕉、一杯白水）才允许 1 项。` +
              `\n6. 不要让 dishes 只有 1 项且名称等于整体餐食名称。` +
              `\n7. 每项 calories 之和应当接近总 calories（允许 ±5% 误差）。` +
              `\n【输出格式 - 严格遵守】` +
              `\n你必须只返回严格JSON，不能返回markdown、不能包含代码块标记、不能有任何解释或额外文字。` +
              `\n返回格式固定为：` +
              `\n{"name":"整体餐食名称（中文，30字内）","calories":整数,"protein":整数,"carbs":整数,"fat":整数,` +
              `"dishes":[{"name":"组件名（10字内）","type":"类别(可选:bread/patty/cheese/meat/vegetable/sauce/oil/rice/topping/seasoning)","calories":整数}]}` +
              `\n单位：calories=千卡，protein/carbs/fat=克，所有数值为整数。`,
          },
        ],
      },
    ],
  })

  const apiRes = await httpsPost(ZHIPU_ENDPOINT, {
    Authorization: `Bearer ${ZHIPU_KEY}`,
  }, body)

  if (!apiRes.choices || !apiRes.choices[0]) {
    throw new Error('API 响应异常: ' + JSON.stringify(apiRes).slice(0, 200))
  }

  const nutrition = parseNutrition(apiRes.choices[0].message.content)
  if (!nutrition) {
    throw new Error('AI 返回格式异常: ' + apiRes.choices[0].message.content.slice(0, 200))
  }
  return refineBreakdown(nutrition)
}

// ── 文字模式：单次识别 ─────────────────────────────────────
async function callZhipuText(text) {
  const body = JSON.stringify({
    model: 'glm-4.7-flash',
    messages: [
      {
        role: 'user',
        content:
          `用户描述了一份食物，请估算1人份营养成分，并将卡路里拆解到"组成部分/配料"级别。` +
          `\n食物描述：「${text}」` +
          `\n【dishes 字段规则 - 非常重要】` +
          `\n1. dishes 必须返回"组成部分级别"的明细，不是整道菜级别。` +
          `\n2. 组合食物（汉堡/三明治/便当/盖饭/沙拉/意面/奶茶等）必须拆成各个组成部分（面包/肉饼/芝士/酱料/米饭/配菜等）。` +
          `\n3. 单品类有调味的食物（蜜汁鸡腿、炸鸡、卤味、烤肉等）拆成 主食材 + 调料/酱汁/裹粉/用油。` +
          `\n4. dishes 至少 3 项；只有真正单一无配料的食物才允许 1 项。` +
          `\n5. 不要让 dishes 只有 1 项且名称等于整体餐食名称。` +
          `\n6. 每项 calories 之和应当接近总 calories（允许 ±5% 误差）。` +
          `\n【输出格式 - 严格遵守】` +
          `\n你必须只返回严格JSON，不能返回markdown、不能包含代码块标记、不能有任何解释或额外文字。` +
          `\n返回格式固定为：` +
          `\n{"name":"食物名称（中文，20字内）","calories":整数,"protein":整数,"carbs":整数,"fat":整数,` +
          `"dishes":[{"name":"组件名（10字内）","type":"类别(可选:bread/patty/cheese/meat/vegetable/sauce/oil/rice/topping/seasoning)","calories":整数}]}` +
          `\n单位：calories=千卡，protein/carbs/fat=克，所有数值为整数。`,
      },
    ],
  })

  const apiRes = await httpsPost(ZHIPU_ENDPOINT, {
    Authorization: `Bearer ${ZHIPU_KEY}`,
  }, body)

  if (!apiRes.choices || !apiRes.choices[0]) {
    throw new Error('API 响应异常: ' + JSON.stringify(apiRes).slice(0, 200))
  }

  const nutrition = parseNutrition(apiRes.choices[0].message.content)
  if (!nutrition) {
    throw new Error('AI 返回格式异常: ' + apiRes.choices[0].message.content.slice(0, 200))
  }
  return refineBreakdown(nutrition)
}

// ── 主函数 ────────────────────────────────────────────────
exports.main = async (event) => {
  const { fileID, hint = '', text = '', mode = 'image' } = event

  if (!ZHIPU_KEY) {
    return { success: false, error: 'ZHIPU_API_KEY 未配置' }
  }

  try {
    // ── 文字模式 ──
    if (mode === 'text') {
      if (!text.trim()) return { success: false, error: '文字描述不能为空' }
      let nutrition
      try {
        nutrition = await callZhipuText(text)
      } catch (firstErr) {
        console.warn('[analyzeMeal] 文字模式首次失败，300ms 后重试:', firstErr.message)
        await delay(300)
        nutrition = await callZhipuText(text)
      }
      return { success: true, ...nutrition }
    }

    // ── 图片模式 ──
    if (!fileID) return { success: false, error: 'fileID 不能为空' }

    // 1. 从云存储下载图片 → base64
    const dl     = await cloud.downloadFile({ fileID })
    const base64 = dl.fileContent.toString('base64')

    // 2. 调用 API，失败后等 800ms 自动重试一次
    let nutrition
    try {
      nutrition = await callZhipu(base64, hint)
    } catch (firstErr) {
      console.warn('[analyzeMeal] 首次识别失败，300ms 后重试:', firstErr.message)
      await delay(300)
      nutrition = await callZhipu(base64, hint)
    }

    return { success: true, ...nutrition }

  } catch (err) {
    console.error('[analyzeMeal] error:', err.message)
    return { success: false, error: err.message }
  }
}
