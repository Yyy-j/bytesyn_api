// components/food-list-item/food-list-item.js
Component({
  properties: {
    mealId:           { type: String,  value: '' },
    name:             { type: String,  value: '' },
    calories:         { type: Number,  value: 0  },
    weight:           { type: Number,  value: 0  },
    protein:          { type: Number,  value: 0  },
    carbs:            { type: Number,  value: 0  },
    fat:              { type: Number,  value: 0  },
    originalCalories: { type: Number,  value: 0  },
    originalProtein:  { type: Number,  value: 0  },
    originalCarbs:    { type: Number,  value: 0  },
    originalFat:      { type: Number,  value: 0  },
    dishes:           { type: Array,   value: []   },
    user:             { type: String,  value: '' },  // 'me' | 'ta'
    userName:         { type: String,  value: '' },
    time:             { type: String,  value: '' },
    canDelete:        { type: Boolean, value: false },
    canEdit:          { type: Boolean, value: false },
  },
  data: {
    detailExpanded: false,
  },
  methods: {
    onTap() {
      this.triggerEvent('tap', { id: this.properties.mealId })
    },
    onToggleDetail() {
      if (!this.properties.dishes || this.properties.dishes.length === 0) return
      this.setData({ detailExpanded: !this.data.detailExpanded })
    },
    onDeleteTap() {
      this.triggerEvent('delete', { id: this.properties.mealId })
    },
    onEditTap() {
      this.triggerEvent('edit', {
        id:               this.properties.mealId,
        originalCalories: this.properties.originalCalories || this.properties.calories,
        originalProtein:  this.properties.originalProtein  || this.properties.protein,
        originalCarbs:    this.properties.originalCarbs    || this.properties.carbs,
        originalFat:      this.properties.originalFat      || this.properties.fat,
      })
    },
  },
})
