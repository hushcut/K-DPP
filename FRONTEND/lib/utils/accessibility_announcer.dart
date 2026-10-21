import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

/// iOS 가 칸 아래 오류 문장을 읽도록 따로 안내할 때까지 기다리는 시간입니다.
///
/// Flutter 의 `FormState.validate` 와 같은 값입니다. 바로 보내면 같은 순간의 화면 갱신
/// 낭독에 끊깁니다.
const Duration fieldErrorAnnouncementDelayOnIOS = Duration(seconds: 1);

/// 폼 검증 밖에서 칸 아래에 띄운 오류 문장을 낭독기에 알립니다.
///
/// `Form.validate()` 는 첫 오류를 스스로 알리지만, 서버 응답으로 붙인 오류(`forceErrorText`)나
/// 칸 하나만 검사한 오류는 알리지 않습니다. 그 둘을 Form 과 같은 방식으로 알립니다.
/// 알림을 지원하지 않는 플랫폼(최근 Android)은 오류 문장이 live region 이라 스스로 읽힙니다.
void announceFieldError(BuildContext context, String message) {
  if (!MediaQuery.supportsAnnounceOf(context)) return;

  final view = View.of(context);
  final textDirection = Directionality.of(context);

  void send() {
    unawaited(
      SemanticsService.sendAnnouncement(
        view,
        message,
        textDirection,
        assertiveness: Assertiveness.assertive,
      ),
    );
  }

  if (defaultTargetPlatform == TargetPlatform.iOS) {
    unawaited(Future<void>.delayed(fieldErrorAnnouncementDelayOnIOS, send));
  } else {
    send();
  }
}
