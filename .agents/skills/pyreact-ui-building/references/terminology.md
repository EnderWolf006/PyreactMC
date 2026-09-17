# 术语约定

- 原生 JsonUI / ModSDK 控件叫 `Control`。
- Pyreact 中所有组件都叫 `Component`。
- 单个原生控件映射到 Pyreact 的组件叫 `Primitive`，包括 `Panel`、`Label`、`Image`、`Item`、`PaperDoll`、`Input`、`Slider`、`ScrollView`、`Button` 等。
- Pyreact 内置且由多个 Primitive 组合成的组件叫 `Composite`，包括 `Dropdown`、`FilledButton`、`ListView`、`Modal`、`SafeArea`、`Toggle` 等。
- 用户态通过 `@Component` 创建的业务组件叫 `Custom Component`。
- 其他概念尽量沿用 React / React Native 叫法。
