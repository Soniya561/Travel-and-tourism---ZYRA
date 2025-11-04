from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from .models import Booking, Payment
from .extensions import db, limiter
import secrets
import stripe

bp = Blueprint('bookings', __name__, url_prefix='/api/bookings')

stripe.api_key = current_app.config['STRIPE_SECRET_KEY']


STEP_TO_PAGE = {
    0: 'booking1.html',
    1: 'booking2.html',
    2: 'booking3.html',
    3: 'booking4.html',
    4: 'checkout.html',
}


def _get_or_create_booking(booking_id: int | None):
    if booking_id:
        return Booking.query.get_or_404(booking_id)
    b = Booking(user_id=current_user.id if current_user.is_authenticated else None)
    db.session.add(b)
    db.session.commit()
    return b


def _attach_to_current_user_if_needed(booking: Booking):
    """Ensure a booking is associated with the logged-in user if not yet bound."""
    if current_user.is_authenticated:
        if booking.user_id is None:
            booking.user_id = current_user.id
            db.session.commit()
        # Enforce ownership
        if booking.user_id != current_user.id:
            return False
    return True


def _recompute_total(booking: Booking) -> float:
    total = 0.0
    sel = booking.selection_data or {}
    try:
        total += float(sel.get('price', 0) or 0)
    except Exception:
        pass
    addons = booking.addons_data or {}
    if isinstance(addons, dict):
        for v in addons.values():
            try:
                total += float(v or 0)
            except Exception:
                continue
    booking.total_amount = round(total, 2)
    return booking.total_amount


def _next_url_for_step(step: int, booking_id: int) -> str | None:
    page = STEP_TO_PAGE.get(step)
    if not page:
        return None
    # Include booking_id as a query param so the next page can continue the flow
    return f"/{page}?booking_id={booking_id}"


@bp.post('/step/<int:step>')
@limiter.limit("30 per hour")
def save_step(step: int):
    # step: 0..4 mapping to booking0..booking4
    payload = request.get_json(silent=True) or {}
    booking_id = payload.get('booking_id')
    booking = _get_or_create_booking(booking_id)

    # Attach ownership if logged in; do not block anonymous users at this stage
    if not _attach_to_current_user_if_needed(booking):
        return jsonify({"error": "Forbidden"}), 403

    if step == 0:
        booking.search_data = payload.get('data')
    elif step == 1:
        booking.selection_data = payload.get('data')
    elif step == 2:
        booking.travelers_data = payload.get('data')
    elif step == 3:
        booking.addons_data = payload.get('data')
    elif step == 4:
        booking.review_data = payload.get('data')
    else:
        return jsonify({"error": "Invalid step"}), 400

    _recompute_total(booking)
    db.session.commit()

    next_url = _next_url_for_step(step, booking.id)
    return jsonify({
        "message": "Saved",
        "booking_id": booking.id,
        "total": booking.total_amount,
        "next_url": next_url,
    })


@bp.post('/confirm')
@login_required
@limiter.limit("20 per hour")
def confirm_booking():
    payload = request.get_json(silent=True) or {}
    booking_id = payload.get('booking_id')
    booking = Booking.query.get_or_404(booking_id)

    # Enforce ownership and attach if needed
    if not _attach_to_current_user_if_needed(booking):
        return jsonify({"error": "Forbidden"}), 403

    # Lock in data before payment
    booking.status = 'in_progress'
    _recompute_total(booking)
    db.session.commit()

    return jsonify({
        "message": "Booking ready for payment",
        "booking_id": booking.id,
        "total": booking.total_amount,
        "next_url": f"/checkout.html?booking_id={booking.id}",
    })


@bp.get('/<int:booking_id>')
@login_required
def get_booking(booking_id: int):
    b = Booking.query.get_or_404(booking_id)
    if b.user_id and b.user_id != current_user.id:
        return jsonify({"error": "Forbidden"}), 403
    return jsonify({
        "id": b.id,
        "status": b.status,
        "total": b.total_amount,
        "search_data": b.search_data,
        "selection_data": b.selection_data,
        "travelers_data": b.travelers_data,
        "addons_data": b.addons_data,
        "review_data": b.review_data,
    })


@bp.post('/create-payment-intent')
@login_required
@limiter.limit("10 per hour")
def create_payment_intent():
    """
    Create a Stripe PaymentIntent for the booking.
    Supports Google Pay via Stripe.
    """
    payload = request.get_json(silent=True) or {}
    booking_id = payload.get('booking_id')

    booking = Booking.query.get_or_404(booking_id)
    if not _attach_to_current_user_if_needed(booking):
        return jsonify({"error": "Forbidden"}), 403

    # Recompute total
    _recompute_total(booking)

    # Create PaymentIntent
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(booking.total_amount * 100),  # Amount in cents
            currency='usd',  # Change to 'inr' if needed
            payment_method_types=['card', 'google_pay'],  # Enable Google Pay
            metadata={'booking_id': booking.id},
        )
        return jsonify({
            'clientSecret': intent.client_secret,
            'paymentIntentId': intent.id,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.post('/pay')
@login_required
@limiter.limit("10 per hour")
def pay():
    """
    Confirm payment with Stripe PaymentIntent.
    - Requires authenticated user
    - Verifies booking ownership
    - Confirms the PaymentIntent
    - Records a Payment row
    """
    payload = request.get_json(silent=True) or {}
    booking_id = payload.get('booking_id')
    payment_intent_id = payload.get('payment_intent_id')

    booking = Booking.query.get_or_404(booking_id)
    if not _attach_to_current_user_if_needed(booking):
        return jsonify({"error": "Forbidden"}), 403

    # Recompute total
    _recompute_total(booking)

    try:
        # Retrieve and confirm the PaymentIntent
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        if intent.status == 'requires_confirmation':
            intent = stripe.PaymentIntent.confirm(payment_intent_id)
        elif intent.status == 'succeeded':
            pass  # Already succeeded
        else:
            return jsonify({"error": "Payment not ready"}), 400

        if intent.status != 'succeeded':
            return jsonify({"error": "Payment failed"}), 400

        # Check amount
        if intent.amount != int(booking.total_amount * 100):
            return jsonify({"error": "Amount mismatch"}), 400

        txn_ref = intent.id  # Use Stripe's ID as txn_ref

        p = Payment(booking_id=booking.id, amount=booking.total_amount, status='success', provider='stripe', txn_ref=txn_ref)
        db.session.add(p)

        booking.status = 'confirmed'
        db.session.commit()

        return jsonify({
            "message": "Payment success",
            "payment_id": p.id,
            "txn_ref": p.txn_ref,
            "booking_id": booking.id,
            "next_url": f"/dashboard.html?booking_id={booking.id}",
        }), 201
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 400


@bp.post('/cancel')
@login_required
@limiter.limit("10 per hour")
def cancel():
    payload = request.get_json(silent=True) or {}
    booking_id = payload.get('booking_id')
    booking = Booking.query.get_or_404(booking_id)

    if not _attach_to_current_user_if_needed(booking):
        return jsonify({"error": "Forbidden"}), 403

    booking.status = 'cancelled'
    db.session.commit()

    return jsonify({"message": "Booking cancelled", "booking_id": booking.id})