import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../theme/app_palette.dart';

/// 알림의 종류입니다. 아이콘·색과 기본 표시 시간이 달라집니다.
///
/// - [success]: 요청한 일이 다 됐다.
/// - [failure]: 요청한 일이 안 됐거나 일부가 안 됐다(부분 실패 포함).
/// - [info]: 요청하지 않은 상태 변화나 대체 처리(세션 만료, 임시 추정값 저장 등).
enum AppBannerKind { success, failure, info }

/// 배너가 닫힌 까닭입니다. debug·profile 빌드의 로그에만 씁니다.
///
/// - [timer]: 표시 시간이 다 됐다.
/// - [tap]·[swipe]: 손가락으로 누르거나 위로 밀었다.
/// - [accessibilityTap]·[accessibilityDismiss]: 읽기 프로그램의 활성화(두 번 탭)·닫기 동작.
/// - [call]: 앱 코드가 [AppBannerHostState.hide] 를 불렀다.
enum AppBannerDismissReason {
  timer,
  tap,
  swipe,
  accessibilityTap,
  accessibilityDismiss,
  call,
}

/// 앱 어디서든 앱바 아래 공용 배너를 띄우는 진입점입니다.
///
/// 스낵바는 스캔 셔터·하단 메뉴를 가렸다. 배너는 Navigator 위에 떠서 화면을 넘어가도
/// 남고, 새 알림이 오면 줄 세우지 않고 바로 바꿉니다(DECISIONS 76·88).
/// `await` 뒤에 띄울 때는 `ScaffoldMessenger` 처럼 [of] 로 먼저 잡아 둡니다.
class AppBanner {
  const AppBanner._();

  /// 앱바(높이 [kToolbarHeight]) 아래로 띄우는 간격입니다.
  /// 앱바 없는 로그인 첫 화면에서도 같은 자리를 씁니다.
  static const double gapBelowAppBar = 8;

  /// 화면 좌우 여백입니다.
  static const double horizontalMargin = 16;

  /// 읽기 프로그램이 켜졌을 때 평소 시간에 곱하는 배수입니다. 배너를 다시 찾아
  /// 듣거나 닫을 여유이며 스위치 제어도 포함합니다. 10초 고정은 그동안 앱바 아래를
  /// 훑으면 그 밑 내용 대신 배너가 읽혀 길었다(DECISIONS 97). 소리는 배너가 사라져도
  /// 끊기지 않는다.
  static const int accessibleNavigationMultiplier = 2;

  /// 낭독 칸을 붙이기 전에 화면이 멈추기를 기다리는 최대 시간입니다.
  ///
  /// 배너는 바로 그리지만 낭독 칸(live region)은 화면 전환·대화상자·시트 애니메이션이
  /// 끝난 뒤에 붙입니다. 전환과 같은 순간에 붙이면 새 화면의 첫 초점이 맨 앞의 배너로
  /// 가서 live region 과 초점으로 두 번 읽혔다(DECISIONS 180). 로딩 표시처럼 끝나지 않는
  /// 애니메이션이 있어도 이 시간이 지나면 붙입니다.
  static const Duration announceWaitLimit = Duration(seconds: 1);

  /// 표시·닫힘을 로그에 남길지입니다. debug·profile 빌드에서 켜지고, release 와
  /// `flutter test`(배너가 뜨는 테스트마다 줄이 쌓인다)에서는 꺼집니다.
  @visibleForTesting
  static bool logEvents =
      !kReleaseMode && !Platform.environment.containsKey('FLUTTER_TEST');

  /// 가장 가까운 [AppBannerHost] 를 돌려줍니다. 없으면 배선 방법을 담은 오류를 냅니다.
  static AppBannerHostState of(BuildContext context) {
    final scope = context.getInheritedWidgetOfExactType<_AppBannerScope>();

    if (scope == null) {
      throw FlutterError.fromParts([
        ErrorSummary('AppBanner.of() 를 AppBannerHost 가 없는 곳에서 불렀습니다.'),
        ErrorHint(
          'MaterialApp 에 builder: AppBannerHost.builder 를 넣어 주세요. '
          '위젯 테스트의 MaterialApp 도 같습니다.',
        ),
      ]);
    }

    return scope.host;
  }

  /// 표시 시간 = 종류 기본값(성공 2.5초, 실패·안내 4초)과 문장 길이 하한 중 큰 쪽입니다.
  ///
  /// 하한은 1초 + 공백을 뺀 글자당 0.1초라 긴 성공 문구나 서버가 보낸 길이를 모르는
  /// 문장도 따라갑니다. 읽기 프로그램이 켜지면 그 시간의
  /// [accessibleNavigationMultiplier] 배입니다(성공 5초, 실패·안내 8초).
  static Duration durationFor(
    String message,
    AppBannerKind kind, {
    bool accessibleNavigation = false,
  }) {
    final characterCount = message.replaceAll(RegExp(r'\s'), '').runes.length;
    final lengthFloor = 1000 + 100 * characterCount;
    final kindDefault = switch (kind) {
      AppBannerKind.success => 2500,
      AppBannerKind.failure || AppBannerKind.info => 4000,
    };
    final usual = math.max(kindDefault, lengthFloor);

    return Duration(
      milliseconds: accessibleNavigation
          ? usual * accessibleNavigationMultiplier
          : usual,
    );
  }
}

/// [MaterialApp.builder] 에 꽂아 Navigator 위에 배너 자리를 두는 위젯입니다.
class AppBannerHost extends StatefulWidget {
  const AppBannerHost({super.key, required this.child});

  /// 보통 MaterialApp 의 Navigator 입니다.
  final Widget child;

  /// `main.dart` 와 위젯 테스트가 함께 쓰는 [MaterialApp.builder] 입니다.
  static Widget builder(BuildContext context, Widget? child) {
    return AppBannerHost(child: child ?? const SizedBox.shrink());
  }

  @override
  State<AppBannerHost> createState() => AppBannerHostState();
}

class AppBannerHostState extends State<AppBannerHost>
    with SingleTickerProviderStateMixin {
  // 지연 초기화(late final = …)로 두면 한 번도 띄우지 않은 호스트가 dispose 에서 처음 만들다
  // 비활성 요소 조회 오류가 난다 → initState 에서 만든다.
  late final AnimationController _controller;
  late final CurvedAnimation _curve;
  late final Animation<Offset> _slide;

  _BannerEntry? _current;
  int _nextSerial = 0;
  Timer? _dismissTimer;

  /// 지금 배너가 뜬 뒤 흐른 시간입니다. 로그에만 씁니다.
  final Stopwatch _shownFor = Stopwatch();

  /// 지금 배너에 낭독 칸을 붙였는지입니다([AppBanner.announceWaitLimit]).
  bool _announced = false;
  Timer? _announceTimer;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 220),
      reverseDuration: const Duration(milliseconds: 180),
    )..addStatusListener(_handleStatusChange);
    _curve = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic,
      reverseCurve: Curves.easeInCubic,
    );
    _slide = Tween<Offset>(
      begin: const Offset(0, -0.4),
      end: Offset.zero,
    ).animate(_curve);
  }

  /// 읽기 프로그램·동작 줄이기에서는 미끄러지지 않고 바로 나타나고 사라집니다.
  bool get _skipsMotion =>
      MediaQuery.accessibleNavigationOf(context) ||
      MediaQuery.disableAnimationsOf(context);

  /// 지금 배너를 [message] 로 바로 바꾸고 시간을 새로 셉니다.
  void show(String message, {required AppBannerKind kind}) {
    if (!mounted) return;

    _dismissTimer?.cancel();

    final previous = _current;
    if (previous != null && _controller.status != AnimationStatus.reverse) {
      _log('바뀜 #${previous.serial} 표시 뒤 ${_shownFor.elapsedMilliseconds}ms');
    }

    final accessibleNavigation = MediaQuery.accessibleNavigationOf(context);
    final duration = AppBanner.durationFor(
      message,
      kind,
      accessibleNavigation: accessibleNavigation,
    );
    final entry = _BannerEntry(
      message: message,
      kind: kind,
      serial: _nextSerial++,
    );

    // 같은 문구가 다시 와도 serial 이 바뀌어 낭독 칸을 새로 만든다.
    // iOS 는 live region 이 새로 생기거나 label 이 바뀔 때만 읽는다.
    setState(() {
      _current = entry;
      _announced = false;
    });
    _shownFor
      ..reset()
      ..start();
    _log(
      '표시 #${entry.serial} ${kind.name} ${duration.inMilliseconds}ms '
      '읽기프로그램=$accessibleNavigation "$message"',
    );
    _announceTimer?.cancel();
    _announceTimer = Timer(
      AppBanner.announceWaitLimit,
      () => _announce(entry.serial),
    );
    SchedulerBinding.instance.addPostFrameCallback(
      (_) => _announceWhenStill(entry.serial),
    );

    if (_skipsMotion) {
      _controller.value = 1;
    } else {
      _controller.forward();
    }

    _dismissTimer = Timer(
      duration,
      () => _dismiss(AppBannerDismissReason.timer),
    );
  }

  /// 프레임이 끝날 때마다 돌아가는 애니메이션이 남았는지 보고, 없으면 낭독 칸을 붙입니다.
  ///
  /// 화면 전환을 띄우는 코드가 배너보다 뒤에 와도 같은 프레임 안이면 그 프레임 끝에는
  /// 전환 애니메이션이 돌고 있다. 배너 자신의 미끄러짐(읽기 프로그램이 꺼졌을 때)도 함께 기다린다.
  void _announceWhenStill(int serial) {
    if (!mounted || _current?.serial != serial || _announced) return;

    if (SchedulerBinding.instance.transientCallbackCount > 0) {
      SchedulerBinding.instance.addPostFrameCallback(
        (_) => _announceWhenStill(serial),
      );
      return;
    }

    _announce(serial);
  }

  void _announce(int serial) {
    _announceTimer?.cancel();
    _announceTimer = null;

    if (!mounted || _current?.serial != serial || _announced) return;

    setState(() => _announced = true);
    _log('낭독 칸 #$serial 표시 뒤 ${_shownFor.elapsedMilliseconds}ms');
  }

  /// 지금 배너를 닫습니다. 없으면 아무 일도 하지 않습니다.
  void hide() => _dismiss(AppBannerDismissReason.call);

  void _dismiss(AppBannerDismissReason reason) {
    _dismissTimer?.cancel();
    _dismissTimer = null;

    final current = _current;
    // 닫히는 중에 다시 불려도(타이머 직후 탭 등) 한 번만 닫고 한 번만 기록한다.
    if (!mounted ||
        current == null ||
        _controller.status == AnimationStatus.reverse) {
      return;
    }

    _log(
      '닫힘 #${current.serial} 이유=${reason.name} '
      '표시 뒤 ${_shownFor.elapsedMilliseconds}ms '
      '읽기프로그램=${MediaQuery.accessibleNavigationOf(context)}',
    );

    if (_skipsMotion) {
      _controller.value = 0;
    } else {
      _controller.reverse();
    }
  }

  void _handleStatusChange(AnimationStatus status) {
    // 닫히는 도중 새 알림이 오면 forward 로 바뀌어 여기까지 오지 않는다.
    if (status == AnimationStatus.dismissed && _current != null && mounted) {
      setState(() => _current = null);
    }
  }

  /// 표시·닫힘을 debug·profile 빌드의 로그(Android 는 logcat 'flutter' 태그)에 남깁니다.
  /// 읽기 프로그램을 켠 기기에서 성공 배너가 5초보다 일찍 닫힌 까닭을 가리려고
  /// 둡니다(DECISIONS 180).
  static void _log(String event) {
    if (!AppBanner.logEvents) return;
    debugPrint('[AppBanner] $event');
  }

  @override
  void dispose() {
    final current = _current;
    if (current != null) {
      _log(
        '호스트 사라짐 #${current.serial} 표시 뒤 ${_shownFor.elapsedMilliseconds}ms',
      );
    }
    _dismissTimer?.cancel();
    _announceTimer?.cancel();
    _curve.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final current = _current;

    return _AppBannerScope(
      host: this,
      child: Stack(
        fit: StackFit.expand,
        children: [
          widget.child,
          if (current != null)
            Positioned(
              top:
                  MediaQuery.paddingOf(context).top +
                  kToolbarHeight +
                  AppBanner.gapBelowAppBar,
              left: AppBanner.horizontalMargin,
              right: AppBanner.horizontalMargin,
              child: _buildTransition(
                // 화면이 멈출 때까지 낭독 트리에서 뺀다([AppBanner.announceWaitLimit]).
                ExcludeSemantics(
                  excluding: !_announced,
                  child: AppBannerView(
                    key: ValueKey<int>(current.serial),
                    message: current.message,
                    kind: current.kind,
                    onDismiss: _dismiss,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildTransition(Widget banner) {
    if (_skipsMotion) return banner;

    return SlideTransition(
      position: _slide,
      child: FadeTransition(opacity: _controller, child: banner),
    );
  }
}

class _BannerEntry {
  const _BannerEntry({
    required this.message,
    required this.kind,
    required this.serial,
  });

  final String message;
  final AppBannerKind kind;
  final int serial;
}

class _AppBannerScope extends InheritedWidget {
  const _AppBannerScope({required this.host, required super.child});

  final AppBannerHostState host;

  @override
  bool updateShouldNotify(_AppBannerScope oldWidget) => host != oldWidget.host;
}

/// 배너 한 장의 모양입니다. 탭하거나 위로 밀면 닫힌 까닭과 함께 [onDismiss] 를 부릅니다.
class AppBannerView extends StatefulWidget {
  const AppBannerView({
    super.key,
    required this.message,
    required this.kind,
    required this.onDismiss,
  });

  final String message;
  final AppBannerKind kind;
  final ValueChanged<AppBannerDismissReason> onDismiss;

  @override
  State<AppBannerView> createState() => _AppBannerViewState();
}

class _AppBannerViewState extends State<AppBannerView> {
  /// 이만큼 위로 끌면 닫습니다.
  static const double _dismissDragDistance = 16;

  /// 짧게 튕겨 올려도 이 속도보다 빠르면 닫습니다.
  static const double _dismissFlingVelocity = 300;

  double _verticalDrag = 0;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final (IconData icon, Color iconColor) = switch (widget.kind) {
      AppBannerKind.success => (Icons.check_circle, Colors.green),
      AppBannerKind.failure => (Icons.error_outline, Colors.redAccent),
      AppBannerKind.info => (Icons.info_outline, AppPalette.accent),
    };

    // 바깥 칸에 label 을 두고 안쪽 Text 를 빼야 한 번만 읽힌다.
    return Semantics(
      container: true,
      liveRegion: true,
      label: widget.message,
      excludeSemantics: true,
      onTap: () => widget.onDismiss(AppBannerDismissReason.accessibilityTap),
      onTapHint: '알림 닫기',
      onDismiss: () =>
          widget.onDismiss(AppBannerDismissReason.accessibilityDismiss),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => widget.onDismiss(AppBannerDismissReason.tap),
        onVerticalDragStart: (_) => _verticalDrag = 0,
        onVerticalDragUpdate: (details) => _verticalDrag += details.delta.dy,
        onVerticalDragEnd: (details) {
          final velocity = details.primaryVelocity ?? 0;

          if (_verticalDrag <= -_dismissDragDistance ||
              velocity <= -_dismissFlingVelocity) {
            widget.onDismiss(AppBannerDismissReason.swipe);
          }
        },
        child: Material(
          color: palette.card,
          elevation: 6,
          shadowColor: Colors.black.withValues(
            alpha: palette.isDark ? 0.5 : 0.18,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: BorderSide(color: palette.border),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon, color: iconColor, size: 22),
                const SizedBox(width: 10),
                Expanded(
                  child: Padding(
                    // 한 줄일 때 글자 가운데가 아이콘(22) 가운데와 맞게 내린다.
                    padding: const EdgeInsets.only(top: 1),
                    child: Text(
                      widget.message,
                      style: TextStyle(
                        color: palette.textPrimary,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        height: 1.4,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
