# -*- coding: utf-8 -*-
# Copyright (c) 2016 The Pycroft Authors. See the AUTHORS file.
# This file is part of the Pycroft project and licensed under the terms of
# the Apache License, Version 2.0. See the LICENSE file for details.
from abc import ABCMeta, abstractmethod
from collections import namedtuple
import csv
from datetime import datetime, date, timedelta
from decimal import Decimal
import difflib
from functools import partial
from itertools import chain, islice, starmap, tee, zip_longest
from io import StringIO
import operator
import re

from sqlalchemy import or_, and_
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import func, between, Integer, cast

from pycroft.helpers.i18n import deferred_gettext, gettext
from pycroft.model import session
from pycroft.model.finance import (
    Account, BankAccount, BankAccountActivity, Semester, Split, Transaction)
from pycroft.helpers.interval import (
    closed, single, Bound, Interval, IntervalSet, UnboundedInterval)
from pycroft.model.functions import sign, least
from pycroft.model.session import with_transaction
from pycroft.model.types import Money
from pycroft.model.user import User


def get_semesters(when=UnboundedInterval):
    """

    :param when:
    :return:
    """
    criteria = []
    if when.begin is not None:
        criteria.append(or_(
            when.begin <= Semester.begins_on,
            between(when.begin, Semester.begins_on, Semester.ends_on)
        ))
    if when.end is not None:
        criteria.append(or_(
            when.end >= Semester.ends_on,
            between(when.end, Semester.begins_on, Semester.ends_on)
        ))
    return Semester.q.filter(*criteria).order_by(Semester.begins_on)


def get_semester_for_date(target_date):
    """
    Get the semester which contains a given target date.
    :param date target_date: The date for which a corresponding semester should
    be found.
    :rtype: Semester
    :raises sqlalchemy.orm.exc.NoResultFound if no semester was found
    :raises sqlalchemy.orm.exc.MultipleResultsFound if multiple semester were
    found.
    """
    return Semester.q.filter(
        between(target_date, Semester.begins_on, Semester.ends_on)
    ).one()


def get_current_semester():
    """
    Get the current semester.
    :rtype: Semester
    """
    return get_semester_for_date(session.utcnow().date())


@with_transaction
def simple_transaction(description, debit_account, credit_account, amount,
                       author, valid_on=None):
    """
    Posts a simple transaction.
    A simple transaction is a transaction that consists of exactly two splits,
    where one account is debited and another different account is credited with
    the same amount.
    The current system date will be used as transaction date, an optional valid
    date may be specified.
    :param unicode description: Description
    :param Account debit_account: Debit (germ. Soll) account.
    :param Account credit_account: Credit (germ. Haben) account
    :param Decimal amount: Amount in Eurocents
    :param User author: User who created the transaction
    :param date valid_on: Date, when the transaction should be valid. Current
    database date, if omitted.
    :type valid_on: date or None
    :rtype: Transaction
    """
    if valid_on is None:
        valid_on = session.utcnow().date()
    new_transaction = Transaction(
        description=description,
        author=author,
        valid_on=valid_on)
    new_debit_split = Split(
        amount=-amount,
        account=debit_account,
        transaction=new_transaction)
    new_credit_split = Split(
        amount=amount,
        account=credit_account,
        transaction=new_transaction)
    session.session.add_all(
        [new_transaction, new_debit_split, new_credit_split]
    )
    return new_transaction


@with_transaction
def complex_transaction(description, author, splits, valid_on=None):
    if valid_on is None:
        valid_on = session.utcnow().date()
    objects = []
    new_transaction = Transaction(
        description=description,
        author=author,
        valid_on=valid_on
    )
    objects.append(new_transaction)
    objects.extend(
        Split(amount=amount, account=account, transaction=new_transaction)
        for (account, amount) in splits
    )
    session.session.add_all(objects)
    return new_transaction


def transferred_amount(from_account, to_account, when=UnboundedInterval):
    """
    Determine how much has been transferred from one account to another in a
    given interval.

    A negative value indicates that more has been transferred from to_account
    to from_account than the other way round.

    The interval boundaries may be None, which indicates no lower and upper
    bound respectively.
    :param Account from_account: source account
    :param Account to_account: destination account
    :param Interval[date] when: Interval in which transactions became valid
    :rtype: int
    """
    split1 = aliased(Split)
    split2 = aliased(Split)
    query = session.session.query(
        cast(func.sum(
            sign(split2.amount) *
            least(func.abs(split1.amount), func.abs(split2.amount))
        ), Money)
    ).select_from(
        split1
    ).join(
        (split2, split1.transaction_id == split2.transaction_id)
    ).join(
        Transaction, split2.transaction_id == Transaction.id
    ).filter(
        split1.account == from_account,
        split2.account == to_account,
        sign(split1.amount) != sign(split2.amount)
    )
    if not when.unbounded:
        query = query.filter(
            between(Transaction.valid_on, when.begin, when.end)
        )
    elif when.begin is not None:
        query = query.filter(Transaction.valid_on >= when.begin)
    elif when.end is not None:
        query = query.filter(Transaction.valid_on <= when.end)
    return query.scalar()


adjustment_description = deferred_gettext(
    u"Correction of „{original_description}“ from {original_valid_on}")


@with_transaction
def post_fees(users, fees, processor):
    """
    Calculate the given fees for all given user accounts from scratch and post
    them if they have not already been posted and correct erroneous postings.
    :param iterable[User] users:
    :param iterable[Fee] fees:
    :param User processor:
    """
    for user in users:
        for fee in fees:
            computed_debts = fee.compute(user)
            posted_transactions = fee.get_posted_transactions(user).all()
            posted_credits = tuple(t for t in posted_transactions if t.amount > 0)
            posted_corrections = tuple(t for t in posted_transactions if t.amount < 0)
            missing_debts, erroneous_debts = diff(posted_credits, computed_debts)
            computed_adjustments = tuple(
                ((adjustment_description.format(
                    original_description=description,
                    original_valid_on=valid_on)).to_json(),
                 valid_on, -amount)
                for description, valid_on, amount in erroneous_debts)
            missing_adjustments, erroneous_adjustments = diff(
                posted_corrections, computed_adjustments
            )
            missing_postings = chain(missing_debts, missing_adjustments)
            today = session.utcnow().date()
            for description, valid_on, amount in missing_postings:
                if valid_on <= today:
                    simple_transaction(
                        description, fee.account, user.account,
                        amount, processor, valid_on)


def diff(posted, computed):
    sequence_matcher = difflib.SequenceMatcher(None, posted, computed)
    missing_postings = []
    erroneous_postings = []
    for tag, i1, i2, j1, j2 in sequence_matcher.get_opcodes():
        if 'replace' == tag:
            erroneous_postings.extend(islice(posted, i1, i2))
            missing_postings.extend(islice(computed, j1, j2))
        if 'delete' == tag:
            erroneous_postings.extend(islice(posted, i1, i2))
        if 'insert' == tag:
            missing_postings.extend(islice(computed, j1, j2))
    return missing_postings, erroneous_postings


def _to_date_interval(interval):
    """
    :param Interval[datetime] interval:
    :rtype: Interval[date]
    """
    if interval.lower_bound.unbounded:
        lower_bound = interval.lower_bound
    else:
        lower_bound = Bound(interval.lower_bound.value.date(),
                            interval.lower_bound.closed)
    if interval.upper_bound.unbounded:
        upper_bound = interval.upper_bound
    else:
        upper_bound = Bound(interval.upper_bound.value.date(),
                            interval.upper_bound.closed)
    return Interval(lower_bound, upper_bound)


def _to_date_intervals(intervals):
    """
    :param IntervalSet[datetime] intervals:
    :rtype: IntervalSet[date]
    """
    return IntervalSet(_to_date_interval(i) for i in intervals)


class Fee(metaclass=ABCMeta):
    """
    Fees must be idempotent, that means if a fee has been applied to a user,
    another application must not result in any change. This property allows
    all the fee to be calculated for all times instead of just the current
    semester or the current day and makes the calculation independent of system
    time it was running.
    """

    validity_period = UnboundedInterval

    def __init__(self, account):
        self.account = account
        self.session = session.session

    def get_posted_transactions(self, user):
        """
        Get all fee transactions that have already been posted to the user's
        finance account.
        :param User user:
        :return:
        :rtype: list[(unicode, date, int)]
        """
        split1 = aliased(Split)
        split2 = aliased(Split)
        transactions = self.session.query(
            Transaction.description, Transaction.valid_on, split1.amount
        ).select_from(Transaction).join(
            (split1, split1.transaction_id == Transaction.id),
            (split2, split2.transaction_id == Transaction.id)
        ).filter(
            split1.account_id == user.account_id,
            split2.account_id == self.account.id
        ).order_by(Transaction.valid_on)
        return transactions

    @abstractmethod
    def compute(self, user):
        """
        Compute all debts the user owes us for this particular fee. Debts must
        be in ascending order of valid_on.

        :param User user:
        :rtype: list[(unicode, date, int)]
        """
        pass


class RegistrationFee(Fee):
    description = deferred_gettext(u"Registration fee").to_json()

    def compute(self, user):
        when = single(user.registered_at)
        if user.has_property("registration_fee", when):
            try:
                semester = get_semester_for_date(user.registered_at.date())
            except NoResultFound:
                return []
            fee = semester.registration_fee
            if fee > 0:
                return [(self.description, user.registered_at.date(), fee)]
        return []


class SemesterFee(Fee):
    description = deferred_gettext(u"Semester fee {semester}")

    def compute(self, user):
        regular_fee_intervals = _to_date_intervals(
            user.property_intervals("semester_fee"))

        reduced_fee_intervals = _to_date_intervals(
            user.property_intervals("reduced_semester_fee"))

        debts = []

        # Compute semester fee for each semester the user is liable to pay it
        semesters = get_semesters()
        for semester in semesters:
            semester_interval = closed(semester.begins_on, semester.ends_on)
            reg_fee_in_semester = regular_fee_intervals & semester_interval
            red_fee_in_semester = reduced_fee_intervals & semester_interval

            # reduced fee trumps regular fee
            reg_fee_in_semester = reg_fee_in_semester - red_fee_in_semester

            # IntervalSet is type-agnostic, so cannot do .length of empty sets,
            # therefore these double checks are required
            if (reg_fee_in_semester and
                        reg_fee_in_semester.length >
                        semester.reduced_semester_fee_threshold):
                amount = semester.regular_semester_fee
                valid_on = reg_fee_in_semester[0].begin

            elif (reg_fee_in_semester and
                        reg_fee_in_semester.length > semester.grace_period):
                amount = semester.reduced_semester_fee
                valid_on = reg_fee_in_semester[0].begin

            elif (red_fee_in_semester and
                        red_fee_in_semester.length > semester.grace_period):
                    amount = semester.reduced_semester_fee
                    valid_on = red_fee_in_semester[0].begin
            else:
                continue

            if amount > 0:
                debts.append((
                    self.description.format(semester=semester.name).to_json(),
                    valid_on, amount))
        return debts


class LateFee(Fee):
    description = deferred_gettext(
        u"Late fee for overdue payment from {original_valid_on}")

    def __init__(self, account, calculate_until):
        """
        :param date calculate_until: Date up until late fees are calculated;
        usually the date of the last bank import
        :param int allowed_overdraft: Amount of overdraft which does not result
        in an late fee being charged.
        :param payment_deadline: Timedelta after which a payment is late
        """
        super(LateFee, self).__init__(account)
        self.calculate_until = calculate_until

    def non_late_fee_transactions(self, user):
        split1 = aliased(Split)
        split2 = aliased(Split)
        return self.session.query(
            Transaction.valid_on, (-func.sum(split2.amount)).label("debt")
        ).select_from(Transaction).join(
            (split1, split1.transaction_id == Transaction.id),
            (split2, split2.transaction_id == Transaction.id)
        ).filter(
            split1.account_id == user.account_id,
            split2.account_id != user.account_id,
            split2.account_id != self.account.id
        ).group_by(
            Transaction.id, Transaction.valid_on
        ).order_by(Transaction.valid_on)

    @staticmethod
    def running_totals(transactions):
        balance = 0
        last_credit = transactions[0][0]
        for valid_on, amount in transactions:
            if amount > 0:
                last_credit = valid_on
            else:
                delta = valid_on - last_credit
                yield last_credit, balance, delta
            balance += amount

    def compute(self, user):
        # Note: User finance accounts are assets accounts from our perspective,
        # that means their balance is positive, if the user owes us money
        transactions = self.non_late_fee_transactions(user).all()
        # Add a pseudo transaction on the day until late fees should be
        # calculated
        transactions.append((self.calculate_until, 0))
        liability_intervals = _to_date_intervals(
            user.property_intervals("late_fee")
        )
        debts = []
        for last_credit, balance, delta in self.running_totals(transactions):
            semester = get_semester_for_date(last_credit)
            if (balance <= semester.allowed_overdraft or
                    delta <= semester.payment_deadline):
                continue
            valid_on = last_credit + semester.payment_deadline + timedelta(days=1)
            amount = semester.late_fee
            if liability_intervals & single(valid_on) and amount > 0:
                debts.append((
                    self.description.format(original_valid_on=last_credit).to_json(),
                    amount, valid_on
                ))
        return debts


MT940_FIELDNAMES = [
    'our_account_number',
    'posted_on',
    'valid_on',
    'type',
    'reference',
    'other_name',
    'other_account_number',
    'other_routing_number',
    'amount',
    'currency',
    'info',
]


MT940Record = namedtuple("MT940Record", MT940_FIELDNAMES)


class MT940Dialect(csv.Dialect):
    delimiter = ";"
    quotechar = '"'
    doublequote = True
    skipinitialspace = True
    lineterminator = '\n'
    quoting = csv.QUOTE_ALL


class CSVImportError(Exception):

    def __init__(self, message, cause=None):
        if cause is not None:
            message = gettext(u"{0}\nCaused by:\n{1}").format(
                message, cause
            )
        self.cause = cause
        super(CSVImportError, self).__init__(message)


def is_ordered(iterable, relation=operator.le):
    """
    Check that an iterable is ordered with respect to a given relation.
    :param iterable[T] iterable: an iterable
    :param (T,T) -> bool op: a binary relation (i.e. a function that returns a bool)
    :return: True, if each element and its successor yield True under the given
    relation.
    :rtype: bool
    """
    a, b = tee(iterable)
    try:
        next(b)
    except StopIteration:
        # iterable is empty
        return True
    return all(relation(x, y) for x, y in zip(a, b))


@with_transaction
def import_bank_account_activities_csv(csv_file, expected_balance,
                                       imported_at=None):
    """
    Import bank account activities from a MT940 CSV file into the database.

    The new activities are merged with the activities that are already saved to
    the database.
    :param csv_file:
    :param expected_balance:
    :param imported_at:
    :return:
    """
    if imported_at is None:
        imported_at = session.utcnow()

    # Convert to MT940Record and enumerate
    reader = csv.reader(csv_file, dialect=MT940Dialect)
    records = enumerate((MT940Record._make(r) for r in reader), 1)
    try:
        # Skip first record (header)
        next(records)
        activities = tuple(process_record(index, record, imported_at=imported_at)
                           for index, record in records)
    except StopIteration:
        raise CSVImportError(gettext(u"No data present."))
    except csv.Error as e:
        raise CSVImportError(gettext(u"Could not read CSV."), e)
    if not activities:
        raise CSVImportError(gettext(u"No data present."))
    if not is_ordered((a[8] for a in activities), operator.ge):
        raise CSVImportError(gettext(
            u"Transaction are not sorted according to transaction date in "
            u"descending order."))
    first_posted_on = activities[-1][8]
    balance = session.session.query(
        func.coalesce(func.sum(BankAccountActivity.amount), 0)
    ).filter(
        BankAccountActivity.posted_on < first_posted_on
    ).scalar()
    a = tuple(session.session.query(
        BankAccountActivity.amount, BankAccountActivity.bank_account_id,
        BankAccountActivity.reference, BankAccountActivity.original_reference,
        BankAccountActivity.other_account_number,
        BankAccountActivity.other_routing_number,
        BankAccountActivity.other_name, BankAccountActivity.imported_at,
        BankAccountActivity.posted_on, BankAccountActivity.valid_on
    ).filter(
        BankAccountActivity.posted_on >= first_posted_on)
    )
    b = tuple(reversed(activities))
    matcher = difflib.SequenceMatcher(a=a, b=b)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if 'equal' == tag:
            continue
        elif 'insert' == tag:
            balance += sum(a[0] for a in islice(activities, j1, j2))
            session.session.add_all(
                BankAccountActivity(
                    amount=e[0], bank_account_id=e[1], reference=e[2],
                    original_reference=e[3], other_account_number=e[4],
                    other_routing_number=e[5], other_name=e[6],
                    imported_at=e[7], posted_on=e[8], valid_on=e[9]
                ) for e in islice(activities, j1, j2)
            )
        elif 'delete' == tag:
            continue
        elif 'replace' == tag:
            raise CSVImportError(
                gettext(u"Import conflict:\n"
                        u"Database bank account activities:\n{0}\n"
                        u"File bank account activities:\n{1}").format(
                    u'\n'.join(str(x) for x in islice(activities, i1, i2)),
                    u'\n'.join(str(x) for x in islice(activities, j1, j2))))
        else:
            raise AssertionError()
    if balance != expected_balance:
        message = gettext(u"Balance after does not equal expected balance: "
                          u"{0} != {1}.")
        raise CSVImportError(message.format(balance, expected_balance))


def remove_space_characters(field):
    """Remove every 28th character if it is a space character."""
    if field is None:
        return None
    return u"".join(c for i, c in enumerate(field) if i % 28 != 27 or c != u' ')


# Banks are using the original reference field to store several subfields with
# SEPA. Subfields start with a four letter tag name and the plus sign, they
# are separated by space characters.
sepa_description_field_tags = (
    u'EREF', u'KREF', u'MREF', u'CRED', u'DEBT', u'SVWZ', u'ABWA', u'ABWE'
)
sepa_description_pattern = re.compile(''.join(chain(
    '^',
    [r'(?:({0}\+.*?)(?: (?!$)|$))?'.format(tag)
     for tag in sepa_description_field_tags],
    '$'
)), re.UNICODE)


def cleanup_description(description):
    match = sepa_description_pattern.match(description)
    if match is None:
        return description
    return u' '.join(remove_space_characters(f) for f in match.groups() if f is not None)


def restore_record(record):
    string_buffer = StringIO()
    csv.DictWriter(
        string_buffer, MT940_FIELDNAMES, dialect=MT940Dialect
    ).writerow(record._asdict())
    restored_record = string_buffer.getvalue()
    string_buffer.close()
    return restored_record


def process_record(index, record, imported_at):
    if record.currency != u"EUR":
        message = gettext(u"Unsupported currency {0}. Record {1}: {2}")
        raw_record = restore_record(record)
        raise CSVImportError(message.format(record.currency, index, raw_record))
    try:
        bank_account = BankAccount.q.filter_by(
            account_number=record.our_account_number
        ).one()
    except NoResultFound as e:
        message = gettext(u"No bank account with account number {0}. "
                          u"Record {1}: {2}")
        raw_record = restore_record(record)
        raise CSVImportError(
            message.format(record.our_account_number, index, raw_record), e)

    try:
        valid_on = datetime.strptime(record.valid_on, u"%d.%m.%y").date()
        posted_on = datetime.strptime(record.posted_on, u"%d.%m.%y").date()
    except ValueError as e:
        message = gettext(u"Illegal date format. Record {1}: {2}")
        raw_record = restore_record(record)
        raise CSVImportError(message.format(index, raw_record), e)

    try:
        amount = Decimal(record.amount.replace(u",", u"."))
    except ValueError as e:
        message = gettext(u"Illegal value format {0}. Record {1}: {2}")
        raw_record = restore_record(record)
        raise CSVImportError(
            message.format(record.amount, index, raw_record), e)

    return (amount, bank_account.id, cleanup_description(record.reference),
            record.reference, record.other_account_number,
            record.other_routing_number, record.other_name, imported_at,
            posted_on, valid_on)


def user_has_paid(user):
    return user.account.balance <= 0


def get_typed_splits(splits):
    splits = sorted(splits, key=lambda s: s.transaction.posted_at, reverse=True)
    return zip_longest(
        (s for s in splits if s.amount >= 0),
        (s for s in splits if s.amount < 0),
    )

def get_transaction_type(transaction):

    credited = [split.account for split in transaction.splits if split.amount>0]
    debited = [split.account for split in transaction.splits if split.amount<0]

    cd_accs = (credited, debited)
    # all involved accounts have the same type:
    if all(all(a.type == accs[0].type for a in accs) for accs in cd_accs)\
            and all(len(accs)>0 for accs in cd_accs):
        return (cd_accs[0][0].type, cd_accs[1][0].type)

def process_transactions(bank_account, statement):
    transactions = []  # new transactions which would be imported
    old_transactions = []  # transactions which are already imported

    for transaction in statement:
        iban = transaction.data['applicant_iban'] if \
            transaction.data['applicant_iban'] is not None else ''
        bic = transaction.data['applicant_bin'] if \
            transaction.data['applicant_bin'] is not None else ''
        other_name = transaction.data['applicant_name'] if \
            transaction.data['applicant_name'] is not None else ''
        new_activity = BankAccountActivity(
            bank_account_id=bank_account.id,
            amount=int(transaction.data['amount'].amount * 100),
            reference=transaction.data['purpose'],
            original_reference=transaction.data['purpose'],
            other_account_number=iban,
            other_routing_number=bic,
            other_name=other_name,
            imported_at=datetime.now(),
            posted_on=transaction.data['entry_date'],
            valid_on=transaction.data['date'],
        )
        if BankAccountActivity.q.filter(and_(
                BankAccountActivity.bank_account_id ==
                new_activity.bank_account_id,
                BankAccountActivity.amount == new_activity.amount,
                BankAccountActivity.reference == new_activity.reference,
                BankAccountActivity.other_account_number ==
                new_activity.other_account_number,
                BankAccountActivity.other_routing_number ==
                new_activity.other_routing_number,
                BankAccountActivity.other_name == new_activity.other_name,
                BankAccountActivity.posted_on == new_activity.posted_on,
                BankAccountActivity.valid_on == new_activity.valid_on
        )).first() is None:
            transactions.append(new_activity)
        else:
            old_transactions.append(new_activity)

    return (transactions, old_transactions)
