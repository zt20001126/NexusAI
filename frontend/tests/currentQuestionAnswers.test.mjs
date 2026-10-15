import assert from 'node:assert/strict'
import test from 'node:test'
import { selectCurrentQuestionAnswers } from '../src/features/chat/model/currentQuestionAnswers.mjs'

test('only submits answers belonging to the current question batch', () => {
  const answers = {
    actual_product: '装饰画',
    image_relation: '图片就是商品本身（如装饰画、海报的画面内容）',
    product_form: '无框帆布画／油画布画',
    size_spec: '30×40',
    material_craft: '棉',
    quantity_included: '不含挂钩',
    brand_status: '无品牌',
    usage_scene: '客厅墙面装饰',
    custom_service: '支持定制尺寸',
    canvas_structure: '已绷内框，收到可直接悬挂',
    size_unit: '30×40 厘米（宽×高）',
    hanging_method: '背面自带挂绳',
    item_quantity: '单幅1件',
    print_or_handmade: '高清数码印刷',
    surface_treatment: '哑光覆膜',
    custom_size_range: '无',
    custom_pattern: '仅支持现有画面，不接图案定制',
    decor_style: '现代简约',
  }

  assert.deepEqual(
    selectCurrentQuestionAnswers(['custom_size_range', 'custom_pattern', 'decor_style'], answers),
    {
      custom_size_range: '无',
      custom_pattern: '仅支持现有画面，不接图案定制',
      decor_style: '现代简约',
    },
  )
})
