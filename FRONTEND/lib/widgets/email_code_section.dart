// 가입·비밀번호 찾기 화면의 [인증번호 받기] 버튼과 인증번호 칸입니다(DECISIONS 170).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/auth_api_service.dart';
import '../theme/app_palette.dart';
import '../utils/accessibility_announcer.dart';
import '../utils/auth_form_validators.dart';
import 'app_banner.dart';
import 'auth_form_widgets.dart';

/// 이메일 칸 바로 아래에 두는 인증번호 요청 버튼과 번호 입력 칸입니다.
///
/// - 번호 칸은 처음부터 보입니다. 요청이 시간 초과로 끝났어도 메일이 왔다면 넣을 수 있습니다.
/// - 남은 시간과 다시 받기 대기는 기기 시계의 마감 시각으로 셉니다. 메일 앱에 다녀오는
///   동안 앱의 타이머가 멈춰도 돌아오면 맞는 값을 보입니다.
/// - 번호는 그 이메일에만 맞으므로, 받은 뒤 이메일을 고치면 번호 칸과 시간을 비웁니다.
///
/// 이 위젯의 번호 칸은 가장 가까운 [Form] 에 들어가 화면의 제출 검사에 함께 걸립니다.
/// 제출 응답의 인증번호 오류는 [EmailCodeSectionState.showSubmitError] 로 넘깁니다.
class EmailCodeSection extends StatefulWidget {
  const EmailCodeSection({
    super.key,
    required this.purpose,
    required this.authApiService,
    required this.emailFieldKey,
    required this.emailController,
    required this.codeController,
    required this.codeFocusNode,
    this.enabled = true,
    this.onCodeSubmitted,
    this.now = DateTime.now,
  });

  final EmailCodePurpose purpose;
  final AuthApiService authApiService;

  /// 번호를 요청하기 전에 이메일 칸만 검사하려고 받습니다.
  final GlobalKey<FormFieldState<String>> emailFieldKey;
  final TextEditingController emailController;
  final TextEditingController codeController;

  /// 번호를 받으면 이 칸으로 옮깁니다. 화면이 숫자 키패드 위 [다음] 버튼을 그릴 때도 씁니다.
  final FocusNode codeFocusNode;

  /// 화면이 제출 중이면 false 입니다. 그동안 번호를 새로 받지 않습니다.
  final bool enabled;

  /// 번호 칸에서 자판의 다음 키를 눌렀을 때 부릅니다.
  final ValueChanged<String>? onCodeSubmitted;

  /// 남은 시간을 셀 현재 시각입니다. 테스트가 시계를 바꿔 끼웁니다.
  final DateTime Function() now;

  @override
  State<EmailCodeSection> createState() => EmailCodeSectionState();
}

class EmailCodeSectionState extends State<EmailCodeSection> {
  Timer? _ticker;
  bool _isRequesting = false;

  /// 지금 화면에 걸린 번호·대기 시간이 어느 이메일(공백 제거·소문자) 것인지입니다.
  String? _targetEmail;

  /// [_targetEmail] 로 번호를 받은 적이 있는지입니다. 버튼 문구가 '다시 받기'로 바뀝니다.
  bool _hasRequested = false;
  DateTime? _expiresAt;
  DateTime? _resendAvailableAt;

  /// 서버가 거절한 이유입니다. 번호 칸 아래에 붙고, 번호를 고치면 지웁니다.
  String? _codeError;

  @override
  void initState() {
    super.initState();
    widget.emailController.addListener(_handleEmailChanged);
  }

  @override
  void didUpdateWidget(EmailCodeSection oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (oldWidget.emailController != widget.emailController) {
      oldWidget.emailController.removeListener(_handleEmailChanged);
      widget.emailController.addListener(_handleEmailChanged);
    }
  }

  @override
  void dispose() {
    widget.emailController.removeListener(_handleEmailChanged);
    _ticker?.cancel();
    super.dispose();
  }

  static String _normalizeEmail(String email) => email.trim().toLowerCase();

  int _secondsUntil(DateTime? deadline) {
    if (deadline == null) return 0;

    final milliseconds = deadline.difference(widget.now()).inMilliseconds;
    return milliseconds <= 0 ? 0 : (milliseconds / 1000).ceil();
  }

  bool get _isWaitingToResend => _secondsUntil(_resendAvailableAt) > 0;

  void _handleEmailChanged() {
    final target = _targetEmail;
    if (target == null) return;
    if (_normalizeEmail(widget.emailController.text) == target) return;

    setState(_resetForNewEmail);
    widget.codeController.clear();
    _syncTicker();
  }

  void _resetForNewEmail() {
    _targetEmail = null;
    _hasRequested = false;
    _expiresAt = null;
    _resendAvailableAt = null;
    _codeError = null;
  }

  /// 남은 시간이나 다시 받기 대기가 있으면 1초마다 다시 그립니다.
  void _syncTicker() {
    final needsTicking =
        _secondsUntil(_expiresAt) > 0 || _secondsUntil(_resendAvailableAt) > 0;

    if (!needsTicking) {
      _ticker?.cancel();
      _ticker = null;
      return;
    }

    _ticker ??= Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {});
      _syncTicker();
    });
  }

  String get _sentMessage => switch (widget.purpose) {
    EmailCodePurpose.signup => '인증번호를 보냈어요. 메일이 오지 않으면 주소를 확인해 주세요.',
    EmailCodePurpose.passwordReset =>
      '가입된 이메일이면 인증번호를 보냈어요. 메일이 오지 않으면 주소를 확인해 주세요.',
  };

  Future<void> _requestCode() async {
    if (_isRequesting || !widget.enabled || _isWaitingToResend) return;

    final emailField = widget.emailFieldKey.currentState;
    if (emailField != null && !emailField.validate()) {
      final error = emailField.errorText;
      if (error != null) announceFieldError(context, error);
      return;
    }

    final email = widget.emailController.text.trim();
    final banner = AppBanner.of(context);

    setState(() => _isRequesting = true);

    try {
      final result = await widget.authApiService.requestEmailCode(
        email: email,
        purpose: widget.purpose,
      );

      if (!mounted) return;

      // 기다리는 동안 이메일을 고쳤으면 번호는 지금 칸의 이메일 것이 아니므로 걸지 않습니다.
      if (_normalizeEmail(widget.emailController.text) ==
          _normalizeEmail(email)) {
        final now = widget.now();

        setState(() {
          _targetEmail = _normalizeEmail(email);
          _hasRequested = true;
          _expiresAt = now.add(Duration(seconds: result.expiresInSeconds));
          _resendAvailableAt = now.add(
            Duration(seconds: result.resendAfterSeconds),
          );
          _codeError = null;
        });
        // 새 번호를 받으면 같은 이메일의 이전 번호는 쓸 수 없습니다.
        widget.codeController.clear();
        _syncTicker();
        widget.codeFocusNode.requestFocus();
      }

      banner.show(_sentMessage, kind: AppBannerKind.success);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      final retryAfter = error.retryAfterSeconds;
      final isWaitLimit =
          error.errorCode == AuthErrorCode.emailCodeResendTooSoon ||
          error.errorCode == AuthErrorCode.tooManyAttempts;

      if (isWaitLimit && retryAfter != null) {
        setState(() {
          if (_targetEmail != _normalizeEmail(email)) {
            _resetForNewEmail();
            _targetEmail = _normalizeEmail(email);
          }
          _resendAvailableAt = widget.now().add(Duration(seconds: retryAfter));
        });
        _syncTicker();
      }

      banner.show(error.userMessage, kind: AppBannerKind.failure);
    } finally {
      if (mounted) {
        setState(() => _isRequesting = false);
      }
    }
  }

  /// 가입·비밀번호 재설정 응답의 인증번호 오류를 번호 칸 아래에 붙이고 낭독기에 알립니다.
  ///
  /// 인증번호 오류가 아니면 아무것도 하지 않고 false 를 돌려줍니다(화면이 배너로 알림).
  bool showSubmitError(AuthApiException error) {
    if (!error.isVerificationCodeError) return false;

    final message = error.userMessage;
    final needsNewCode =
        error.errorCode == AuthErrorCode.verificationCodeResendRequired;

    setState(() {
      _codeError = message;
      // 서버가 그 번호를 버렸으므로 남은 시간을 더 보이지 않습니다.
      if (needsNewCode) _expiresAt = null;
    });

    if (needsNewCode) {
      widget.codeController.clear();
    } else {
      // 남은 기회 안에서 고칠 수 있게 번호 칸으로 옮깁니다.
      widget.codeFocusNode.requestFocus();
    }

    _syncTicker();
    announceFieldError(context, message);
    return true;
  }

  String get _requestButtonLabel {
    final label = _hasRequested ? '인증번호 다시 받기' : '인증번호 받기';
    final wait = _secondsUntil(_resendAvailableAt);

    return wait > 0 ? '$label (${formatAuthWait(wait)} 후)' : label;
  }

  Widget _buildCodeHelper(BuildContext context) {
    // InputDecoration.helper 위젯에는 helperText 의 글자 모양이 붙지 않아 같은 값을 직접 줍니다.
    final theme = Theme.of(context);
    final style = theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );

    Text helperText(String text, {String? semanticsLabel}) =>
        Text(text, style: style, maxLines: 2, semanticsLabel: semanticsLabel);

    if (!_hasRequested) {
      return helperText(switch (widget.purpose) {
        EmailCodePurpose.signup => '인증번호 받기를 누르면 메일로 6자리 숫자를 보내 드려요',
        EmailCodePurpose.passwordReset =>
          '인증번호 받기를 누르면 가입된 이메일로 6자리 숫자를 보내 드려요',
      });
    }

    if (_expiresAt == null) {
      return helperText('인증번호를 다시 받아 주세요');
    }

    final remaining = _secondsUntil(_expiresAt);
    if (remaining <= 0) {
      return helperText('유효 시간이 지났어요. 인증번호를 다시 받아 주세요.');
    }

    final minutes = remaining ~/ 60;
    final seconds = remaining % 60;

    // 화면은 '9:58', 낭독기는 '9분 58초'로 읽습니다. 1초마다 바뀌므로 live region 이 아닙니다.
    return helperText(
      '남은 시간 $minutes:${seconds.toString().padLeft(2, '0')}',
      semanticsLabel: seconds == 0
          ? '남은 시간 $minutes분'
          : minutes == 0
          ? '남은 시간 $seconds초'
          : '남은 시간 $minutes분 $seconds초',
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final canRequest = widget.enabled && !_isRequesting && !_isWaitingToResend;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 52,
          child: OutlinedButton(
            onPressed: canRequest ? _requestCode : null,
            style: OutlinedButton.styleFrom(
              foregroundColor: AppPalette.accent,
              side: BorderSide(
                color: canRequest
                    ? AppPalette.accent
                    : AppPalette.accent.withValues(alpha: 0.35),
                width: 1.5,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(26),
              ),
            ),
            child: _isRequesting
                ? Semantics(
                    label: '인증번호 요청 중',
                    liveRegion: true,
                    child: const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.2,
                        color: AppPalette.accent,
                      ),
                    ),
                  )
                : Text(
                    _requestButtonLabel,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
          ),
        ),
        const SizedBox(height: 16),
        TextFormField(
          controller: widget.codeController,
          focusNode: widget.codeFocusNode,
          keyboardType: TextInputType.number,
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.oneTimeCode],
          autocorrect: false,
          enableSuggestions: false,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(6),
          ],
          validator: validateVerificationCode,
          forceErrorText: _codeError,
          onChanged: (_) {
            if (_codeError == null) return;
            setState(() => _codeError = null);
          },
          onFieldSubmitted: widget.onCodeSubmitted,
          style: TextStyle(color: palette.textPrimary),
          cursorColor: AppPalette.accent,
          decoration: authInputDecoration(
            context,
            labelText: '인증번호',
            hintText: '6자리 숫자',
            helper: _buildCodeHelper(context),
          ),
        ),
      ],
    );
  }
}
