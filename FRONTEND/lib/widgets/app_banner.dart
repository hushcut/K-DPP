import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/app_palette.dart';

/// 알림의 종류입니다. 아이콘·색과 기본 표시 시간이 달라집니다.
///
/// - [success]: 요청한 일이 다 됐다.
/// - [failure]: 요청한 일이 안 됐거나 일부가 안 됐다(부분 실패 포함).
/// - [info]: 요청하지 않은 상태 변화나 대체 처리(세션 만료, 임시 추정값 저장 등).
enum AppBannerKind { success, failure, info }

/// 앱 어디서든 앱바 아래 공용 배너를 띄우는 진입점입니다.
///
/// 스낵바는 스캔 셔터·하단 메뉴를 가렸다. 배너는 Navigator 위에 떠서 화면을 넘어가도
/// 남고, 새 알림이 오면 줄 세우지 않고 바로 바꿉니다(DECISIONS 76·88).
/// `await` 뒤에 띄울 때는 `ScaffoldMessenger` 처럼 [of] 로 먼저 잡아 둡니다.
class AppBanner {
  const AppBanner._();

  /// 앱바(높이 [kToolbarHeight]) 아래로 띄우는 간격입니다.
  /// 리포트(앱바 44)나 앱바 없는 로그인 첫 화면에서도 같은 자리를 씁니다.
  static const double gapBelowAppBar = 8;

  /// 화면 좌우 여백입니다.
  static const double horizontalMargin = 16;

  /// 읽기 프로그램이 켜졌을 때 평소 시간에 곱하는 배수입니다. 배너를 다시 찾아
  /// 듣거나 닫을 여유이며 스위치 제어도 포함합니다. 10초 고정은 그동안 앱바 아래를
  /// 훑으면 그 밑 내용 대신 배너가 읽혀 길었다(DECISIONS 97). 소리는 배너가 사라져도
  /// 끊기지 않는다.
  static const int accessibleNavigationMultiplier = 2;

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

    // 같은 문구가 다시 와도 serial 이 바뀌어 낭독 칸을 새로 만든다.
    // iOS 는 live region 이 새로 생기거나 label 이 바뀔 때만 읽는다.
    setState(() {
      _current = _BannerEntry(message: message, kind: kind, serial: _nextSerial++);
    });

    if (_skipsMotion) {
      _controller.value = 1;
    } else {
      _controller.forward();
    }

    _dismissTimer = Timer(
      AppBanner.durationFor(
        message,
        kind,
        accessibleNavigation: MediaQuery.accessibleNavigationOf(context),
      ),
      hide,
    );
  }

  /// 지금 배너를 닫습니다. 없으면 아무 일도 하지 않습니다.
  void hide() {
    _dismissTimer?.cancel();
    _dismissTimer = null;

    if (!mounted || _current == null) return;

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

  @override
  void dispose() {
    _dismissTimer?.cancel();
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
                AppBannerView(
                  key: ValueKey<int>(current.serial),
                  message: current.message,
                  kind: current.kind,
                  onDismiss: hide,
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

/// 배너 한 장의 모양입니다. 탭하거나 위로 밀면 [onDismiss] 를 부릅니다.
class AppBannerView extends StatefulWidget {
  const AppBannerView({
    super.key,
    required this.message,
    required this.kind,
    required this.onDismiss,
  });

  final String message;
  final AppBannerKind kind;
  final VoidCallback onDismiss;

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
      onTap: widget.onDismiss,
      onTapHint: '알림 닫기',
      onDismiss: widget.onDismiss,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onDismiss,
        onVerticalDragStart: (_) => _verticalDrag = 0,
        onVerticalDragUpdate: (details) => _verticalDrag += details.delta.dy,
        onVerticalDragEnd: (details) {
          final velocity = details.primaryVelocity ?? 0;

          if (_verticalDrag <= -_dismissDragDistance ||
              velocity <= -_dismissFlingVelocity) {
            widget.onDismiss();
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
