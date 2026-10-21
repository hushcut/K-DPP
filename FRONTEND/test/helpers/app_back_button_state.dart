import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/widgets/app_back_button.dart';

/// 맨 위 화면의 "<"([AppBackButton])가 눌리는지입니다. 막히면 흐리게 그려지고 TalkBack 은
/// '사용 중지됨'으로 읽습니다(app_glass_button_test.dart).
bool isAppBackButtonEnabled(WidgetTester tester) =>
    tester
        .widget<IconButton>(
          find.descendant(
            of: find.byType(AppBackButton),
            matching: find.byType(IconButton),
          ),
        )
        .onPressed !=
    null;

/// "<" 와 시스템 뒤로가기로 맨 위 화면을 떠나 보고, 떠났다면 끝났을 만큼 시간을 넘깁니다.
///
/// 서버 요청을 붙잡아 둔 채 부르므로 `pumpAndSettle` 은 쓰지 않습니다 — 도는 표시 때문에 가짜
/// 시간이 요청 시간 초과까지 넘어갑니다.
Future<void> tryToLeave(WidgetTester tester) async {
  await tester.tap(find.byType(AppBackButton));
  await pumpPastTransition(tester);
  await tester.binding.handlePopRoute();
  await pumpPastTransition(tester);
}

/// 화면 전환이 끝날 만큼 두 프레임을 넘깁니다. 한 프레임만 넘기면 새로 쌓인 화면은 아직
/// offstage(첫 프레임은 화면 밖에서 그림)라 기본 찾기에 안 잡히고, 닫히는 화면은 아직 남아 있습니다.
Future<void> pumpPastTransition(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
}
