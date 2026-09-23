import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// 화면에 보이는 누름 효과(InkWell·ListTile 등의 물결·강조)를 색 칠한 바탕이 덮고 있는 곳을 찾습니다.
///
/// 누름 효과는 가장 가까운 [Material] 에 그려지고, 그 Material 의 자식들보다 **먼저** 칠해집니다.
/// 그래서 Material 과 InkWell 사이에 있거나 InkWell 을 통째로 채우는 색 칠한 상자
/// (`Container(color:)`·`Container(decoration:)`·채움 입력칸)가 있으면 효과가 그 아래에 가려집니다
/// (2026-09-24 폰 확인: 옷장 카드·설정 칸을 눌러도 눌린 표시가 없었다).
///
/// 돌려주는 목록의 각 줄은 가려진 효과와 가린 위젯을 적습니다. 비어 있으면 통과입니다.
List<String> findCoveredInk(WidgetTester tester) {
  final problems = <String>[];

  for (final element in find
      .byWidgetPredicate((widget) => widget is InkResponse)
      .evaluate()) {
    final ink = element.widget as InkResponse;
    if (ink.onTap == null && ink.onLongPress == null) continue;

    final inkBox = element.renderObject;
    if (inkBox is! RenderBox || !inkBox.hasSize) continue;
    final name = _describe(element);

    // 효과를 그리는 Material 까지 올라가며 사이에 색 칠한 상자가 있는지 봅니다.
    element.visitAncestorElements((ancestor) {
      if (ancestor.widget is Material) return false;
      if (_paintsFill(ancestor.widget)) {
        problems.add('$name ← 위에서 ${ancestor.widget.runtimeType} 가 덮음');
      }
      return true;
    });

    // 효과 영역을 거의 다 채우는 자식 상자도 효과를 덮습니다(아이콘 칸처럼 작은 것은 괜찮음).
    void visit(Element child) {
      if (child.widget is Material) return;
      final box = child.renderObject;
      if (_paintsFill(child.widget) &&
          box is RenderBox &&
          box.hasSize &&
          box.size.width >= inkBox.size.width * 0.9 &&
          box.size.height >= inkBox.size.height * 0.9) {
        problems.add('$name ← 안에서 ${child.widget.runtimeType} 가 덮음');
      }
      child.visitChildren(visit);
    }

    element.visitChildren(visit);
  }

  return problems;
}

bool _paintsFill(Widget widget) {
  if (widget is ColoredBox) return widget.color.a > 0;
  if (widget is DecoratedBox) {
    if (widget.position != DecorationPosition.background) return false;
    final decoration = widget.decoration;
    if (decoration is BoxDecoration) {
      return (decoration.color?.a ?? 0) > 0 || decoration.gradient != null;
    }
    if (decoration is ShapeDecoration) {
      return (decoration.color?.a ?? 0) > 0 || decoration.gradient != null;
    }
    return false;
  }
  if (widget is InputDecorator) {
    final decoration = widget.decoration;
    return decoration.filled == true && (decoration.fillColor?.a ?? 1) > 0;
  }
  return false;
}

/// 실패 메시지에서 어느 효과인지 알아볼 수 있게 안의 글자를 붙입니다.
String _describe(Element element) {
  final texts = <String>[];
  void collect(Element child) {
    final widget = child.widget;
    if (widget is Text && widget.data != null) texts.add(widget.data!);
    if (widget is Icon && widget.semanticLabel != null) {
      texts.add(widget.semanticLabel!);
    }
    child.visitChildren(collect);
  }

  element.visitChildren(collect);
  final label = texts.isEmpty ? '(글자 없음)' : texts.take(2).join(' / ');
  return '${element.widget.runtimeType}「$label」';
}
