# Vyper version of the Lendroid protocol v1
# Audit report available at:
# https://certificate.quantstamp.com/view/lendroid-protocol-version-1-0


# struct representing a kernel
struct Kernel:
    lender: address
    borrower: address
    relayer: address
    wrangler: address
    borrow_currency_address: address
    lend_currency_address: address
    lend_currency_offered_value: uint256
    relayer_fee: uint256
    monitoring_fee: uint256
    rollover_fee: uint256
    closure_fee: uint256
    salt: bytes32
    expires_at: timestamp
    daily_interest_rate: uint256
    position_duration_in_seconds: timedelta

# struct representing a position
struct Position:
    index: uint256
    kernel_creator: address
    lender: address
    borrower: address
    relayer: address
    wrangler: address
    created_at: timestamp
    updated_at: timestamp
    expires_at: timestamp
    borrow_currency_address: address
    lend_currency_address: address
    borrow_currency_value: uint256
    borrow_currency_current_value: uint256
    lend_currency_filled_value: uint256
    lend_currency_owed_value: uint256
    status: uint256
    nonce: uint256
    relayer_fee: uint256
    monitoring_fee: uint256
    rollover_fee: uint256
    closure_fee: uint256
    hash: bytes32

# Interface for the ERC20 contract, used mainly for `transfer` and `transferFrom` functions
contract ERC20:
    def name() -> string[64]: constant
    def symbol() -> string[32]: constant
    def decimals() -> uint256: constant
    def balanceOf(_owner: address) -> uint256: constant
    def totalSupply() -> uint256: constant
    def transfer(_to: address, _amount: uint256) -> bool: modifying
    def transferFrom(_from: address, _to: address, _value: uint256) -> bool: modifying
    def approve(_spender: address, _amount: uint256) -> bool: modifying
    def allowance(_owner: address, _spender: address) -> uint256: constant

# Events of the protocol.
ProtocolParameterUpdateNotification: event({_notification_key: string[64], _address: indexed(address), _notification_value: uint256})
PositionUpdateNotification: event({_wrangler: indexed(address), _position_hash: indexed(bytes32), _notification_key: string[64], _notification_value: uint256})

# Variables of the protocol.
protocol_token_address: public(address)
owner: public(address)
# kernel
kernels_filled: public(map(bytes32, uint256))
kernels_cancelled: public(map(bytes32, uint256))
# all positions
positions: public(map(bytes32, Position))
last_position_index: public(uint256)
position_index: public(map(uint256, bytes32))
position_threshold: public(uint256)
borrow_positions: public(map(address, map(uint256, bytes32)))
lend_positions: public(map(address, map(uint256, bytes32)))
borrow_position_index: map(address, map(bytes32, uint256))
lend_position_index: map(address, map(bytes32, uint256))
borrow_positions_count: public(map(address, uint256))
lend_positions_count: public(map(address, uint256))

# wrangler
wranglers: public(map(address, bool))
wrangler_nonces: public(map(address, map(address, uint256)))

# tokens
supported_tokens: public(map(address, bool))

# nonreentrant locks for positions, inspired from https://github.com/ethereum/vyper/issues/1204
nonreentrant_locks: map(bytes32, bool)

# constants
SECONDS_PER_DAY: public(uint256)
POSITION_STATUS_OPEN: public(uint256)
POSITION_STATUS_CLOSED: public(uint256)
POSITION_STATUS_LIQUIDATED: public(uint256)
POSITION_TOPPED_UP: public(uint256)


@public
def __init__(_protocol_token_address: address):
    self.owner = msg.sender
    self.protocol_token_address = _protocol_token_address
    self.position_threshold = 10
    self.SECONDS_PER_DAY = 86400
    self.POSITION_STATUS_OPEN = 1
    self.POSITION_STATUS_CLOSED = 2
    self.POSITION_STATUS_LIQUIDATED = 3
    self.POSITION_TOPPED_UP = 1


# constant functions
@public
@constant
def ecrecover_from_signature(_hash: bytes32, _sig: bytes[65]) -> address:
    """
    @info Inspired from https://github.com/LayerXcom/verified-vyper-contracts/blob/master/contracts/ecdsa/ECDSA.vy
    @dev Recover signer address from a message by using their signature
    @param _hash bytes32 message, the hash is the signed message. What is recovered is the signer address.
    @param _sig bytes signature, the signature is generated using web3.eth.sign()
    """
    if len(_sig) != 65:
        return ZERO_ADDRESS
    v: int128 = convert(slice(_sig, start=64, len=1), int128)
    if v < 27:
        v += 27
    if v in [27, 28]:
        return ecrecover(_hash, convert(v, uint256), extract32(_sig, 0, type=uint256), extract32(_sig, 32, type=uint256))
    return ZERO_ADDRESS


@public
@constant
def is_signer(_prover: address, _hash: bytes32, _sig: bytes[65]) -> bool:
    if _prover == self.ecrecover_from_signature(_hash, _sig):
        return True
    else:
        sign_prefix: bytes[32] = "\x19Ethereum Signed Message:\n32"
        return _prover == self.ecrecover_from_signature(sha3(concat(sign_prefix, _hash)), _sig)


@public
@constant
def can_borrow(_address: address) -> bool:
    return self.borrow_positions_count[_address] < self.position_threshold


@public
@constant
def can_lend(_address: address) -> bool:
    return self.lend_positions_count[_address] < self.position_threshold


@public
@constant
def filled_or_cancelled_loan_amount(_kernel_hash: bytes32) -> uint256:
    return as_unitless_number(self.kernels_filled[_kernel_hash]) + as_unitless_number(self.kernels_cancelled[_kernel_hash])


@public
@constant
def position(_position_hash: bytes32) -> (uint256, address, address, address, address, address, timestamp, timestamp, timestamp, address, address, uint256, uint256,
    uint256, uint256, uint256, uint256, uint256, uint256, uint256, uint256, bytes32):
    return (self.positions[_position_hash].index, self.positions[_position_hash].kernel_creator, self.positions[_position_hash].lender, self.positions[_position_hash].borrower, self.positions[_position_hash].relayer, self.positions[_position_hash].wrangler, self.positions[_position_hash].created_at, self.positions[_position_hash].updated_at, self.positions[_position_hash].expires_at, self.positions[_position_hash].borrow_currency_address, self.positions[_position_hash].lend_currency_address, self.positions[_position_hash].borrow_currency_value, self.positions[_position_hash].borrow_currency_current_value, self.positions[_position_hash].lend_currency_filled_value, self.positions[_position_hash].lend_currency_owed_value, self.positions[_position_hash].status, self.positions[_position_hash].nonce, self.positions[_position_hash].relayer_fee, self.positions[_position_hash].monitoring_fee, self.positions[_position_hash].rollover_fee, self.positions[_position_hash].closure_fee, self.positions[_position_hash].hash)


@public
@constant
def position_counts(_address: address) -> (uint256, uint256):
    return (self.borrow_positions_count[_address], self.lend_positions_count[_address])


@public
@constant
def kernel_hash(
        _addresses: address[6], _values: uint256[5],
        _kernel_expires_at: timestamp, _creator_salt: bytes32,
        _daily_interest_rate: uint256, _position_duration_in_seconds: timedelta
        ) -> bytes32:
    return sha3(
        concat(
            convert(self, bytes32),
            convert(_addresses[0], bytes32),# lender
            convert(_addresses[1], bytes32),# borrower
            convert(_addresses[2], bytes32),# relayer
            convert(_addresses[3], bytes32),# wrangler
            convert(_addresses[4], bytes32),# collateralToken
            convert(_addresses[5], bytes32),# loanToken
            convert(_values[0], bytes32),# loanAmountOffered
            convert(_values[1], bytes32),# relayerFeeLST
            convert(_values[2], bytes32),# monitoringFeeLST
            convert(_values[3], bytes32),# rolloverFeeLST
            convert(_values[4], bytes32),# closureFeeLST
            _creator_salt,# creatorSalt
            convert(_kernel_expires_at, bytes32),# offerExpiryTimestamp
            convert(_daily_interest_rate, bytes32),# loanInterestRatePerDay
            convert(_position_duration_in_seconds, bytes32)# loanDuration
        )
    )


@public
@constant
def position_hash(
            _addresses: address[7],
            # _addresses: kernel_creator, lender, borrower, relayer, wrangler, collateralToken, loanToken
            _values: uint256[7],
            # _values: collateralAmount, loanAmountOffered, relayerFeeLST, monitoringFeeLST, rolloverFeeLST, closureFeeLST, loanAmountFilled
            _lend_currency_owed_value: uint256, _nonce: uint256
        ) -> bytes32:
    return sha3(
        concat(
            convert(self, bytes32),
            convert(_addresses[5], bytes32),# collateralToken
            convert(_addresses[6], bytes32),# loanToken
            convert(_values[0], bytes32),# collateralAmount
            convert(_values[6], bytes32),# loanAmountFilled
            convert(_lend_currency_owed_value, bytes32),# loanAmountOwed
            convert(_addresses[0], bytes32),# kernel_creator
            convert(_addresses[1], bytes32),# lender
            convert(_addresses[2], bytes32),# borrower
            convert(_addresses[3], bytes32),# relayer
            convert(_addresses[4], bytes32),# wrangler
            convert(_values[2], bytes32),# relayerFeeLST
            convert(_values[3], bytes32),# monitoringFeeLST
            convert(_values[4], bytes32),# rolloverFeeLST
            convert(_values[5], bytes32),# closureFeeLST
            convert(_nonce, bytes32)# nonce
        )
    )


@public
@constant
def owed_value(
        _filled_value: uint256,
        _kernel_daily_interest_rate: uint256,
        _position_duration_in_seconds: timedelta
    ) -> uint256:
    # calculate owed value
    _position_duration_in_days: uint256 = as_unitless_number(_position_duration_in_seconds) / as_unitless_number(self.SECONDS_PER_DAY)
    _total_interest: uint256 = as_unitless_number(_filled_value) * as_unitless_number(_position_duration_in_days) * as_unitless_number(_kernel_daily_interest_rate) / 10 ** 20
    return as_unitless_number(_filled_value) + as_unitless_number(_total_interest)


# escape hatch functions
@public
def escape_hatch_token(_token_address: address) -> bool:
    assert msg.sender == self.owner
    # transfer token from this address to owner (message sender)
    token_transfer: bool = ERC20(_token_address).transfer(
        msg.sender,
        ERC20(_token_address).balanceOf(self)
    )
    assert token_transfer
    return True


# protocol parameter functions
@public
def set_position_threshold(_value: uint256) -> bool:
    assert msg.sender == self.owner
    self.position_threshold = _value
    log.ProtocolParameterUpdateNotification("position_threshold", ZERO_ADDRESS, _value)
    return True


@public
def set_wrangler_status(_address: address, _is_active: bool) -> bool:
    assert msg.sender == self.owner
    self.wranglers[_address] = _is_active
    log.ProtocolParameterUpdateNotification("wrangler_status", _address, convert(_is_active, uint256))
    return True


@public
def set_token_support(_address: address, _is_active: bool) -> bool:
    assert msg.sender == self.owner
    assert _address.is_contract
    self.supported_tokens[_address] = _is_active
    log.ProtocolParameterUpdateNotification("token_support", _address, convert(_is_active, uint256))
    return True


# internal functions
@private
def lock_position(_position_hash: bytes32):
    assert self.nonreentrant_locks[_position_hash] == False
    self.nonreentrant_locks[_position_hash] = True


@private
def unlock_position(_position_hash: bytes32):
    assert self.nonreentrant_locks[_position_hash] == True
    self.nonreentrant_locks[_position_hash] = False


@private
def record_position(_lender: address, _borrower: address, _position_hash: bytes32):
    assert self.can_borrow(_borrower)
    assert self.can_lend(_lender)
    # borrow position
    self.borrow_positions_count[_borrower] += 1
    self.borrow_position_index[_borrower][_position_hash] = self.borrow_positions_count[_borrower]
    self.borrow_positions[_borrower][self.borrow_positions_count[_borrower]] = _position_hash
    # lend position
    self.lend_positions_count[_lender] += 1
    self.lend_position_index[_lender][_position_hash] = self.lend_positions_count[_lender]
    self.lend_positions[_lender][self.lend_positions_count[_lender]] = _position_hash


@private
def remove_position(_position_hash: bytes32):
    _borrower: address = self.positions[_position_hash].borrower
    _lender: address = self.positions[_position_hash].lender
    # update borrow position indices
    _current_position_index: uint256 = self.borrow_position_index[_borrower][_position_hash]
    _last_position_index: uint256 = self.borrow_positions_count[_borrower]
    _last_position_hash: bytes32 = self.borrow_positions[_borrower][_last_position_index]
    self.borrow_positions[_borrower][_current_position_index] = self.borrow_positions[_borrower][_last_position_index]
    self.borrow_positions[_borrower][_last_position_index] = EMPTY_BYTES32
    self.borrow_position_index[_borrower][_position_hash] = 0
    self.borrow_position_index[_borrower][_last_position_hash] = _current_position_index
    self.borrow_positions_count[_borrower] -= 1
    # update lend position indices
    _current_position_index = self.lend_position_index[_lender][_position_hash]
    _last_position_index = self.lend_positions_count[_lender]
    _last_position_hash = self.lend_positions[_lender][_last_position_index]
    self.lend_positions[_lender][_current_position_index] = self.lend_positions[_lender][_last_position_index]
    self.lend_positions[_lender][_last_position_index] = EMPTY_BYTES32
    self.lend_position_index[_lender][_position_hash] = 0
    self.lend_position_index[_lender][_last_position_hash] = _current_position_index
    self.lend_positions_count[_lender] -= 1


@public
def open_position(
        _kernel_creator: address,
        _addresses: address[6],
        # _addresses: lender, borrower, relayer, wrangler, collateralToken, loanToken
        _values: uint256[7],
        # _values: collateralAmount, loanAmountOffered, relayerFeeLST, monitoringFeeLST, rolloverFeeLST, closureFeeLST, loanAmountFilled (aka, loanAmountBorrowed)
        _nonce: uint256,
        _kernel_daily_interest_rate: uint256,
        _position_duration_in_seconds: timedelta,
        _approval_expires: timestamp,
        _sig_data: bytes[65]
        # v, r, s of wrangler
    ):
    # this is a `fake internal` function for now!
    assert msg.sender == self
    # calculate owed value
    _lend_currency_owed_value: uint256 = self.owed_value(_values[6], _kernel_daily_interest_rate, _position_duration_in_seconds)
    # create position from struct
    _new_position: Position = Position({
        index: self.last_position_index,
        kernel_creator: _kernel_creator,
        lender: _addresses[0],
        borrower: _addresses[1],
        relayer: _addresses[2],
        wrangler: _addresses[3],
        created_at: block.timestamp,
        updated_at: block.timestamp,
        expires_at: block.timestamp + _position_duration_in_seconds,
        borrow_currency_address: _addresses[4],
        lend_currency_address: _addresses[5],
        borrow_currency_value: _values[0],
        borrow_currency_current_value: _values[0],
        lend_currency_filled_value: _values[6],
        lend_currency_owed_value: _lend_currency_owed_value,
        status: self.POSITION_STATUS_OPEN,
        nonce: _nonce,
        relayer_fee: _values[2],
        monitoring_fee: _values[3],
        rollover_fee: _values[4],
        closure_fee: _values[5],
        hash: self.position_hash([_kernel_creator, _addresses[0], _addresses[1],
            _addresses[2], _addresses[3], _addresses[4], _addresses[5]],
            _values, _lend_currency_owed_value, _nonce
        )
    })
    # lock position_non_reentrant before loan creation
    self.lock_position(_new_position.hash)
    # validate wrangler's activation status
    assert self.wranglers[_new_position.wrangler]
    # validate wrangler's approval expiry
    assert _approval_expires > block.timestamp
    # validate wrangler's nonce
    assert _nonce == self.wrangler_nonces[_new_position.wrangler][_kernel_creator] + 1
    # increment wrangler's nonce for kernel creator
    self.wrangler_nonces[_new_position.wrangler][_kernel_creator] += 1
    # validate wrangler's signature
    assert self.is_signer(_new_position.wrangler, _new_position.hash, _sig_data)
    # update position index
    self.position_index[self.last_position_index] = _new_position.hash
    self.last_position_index += 1
    self.positions[_new_position.hash] = _new_position
    # record position
    self.record_position(_addresses[0], _addresses[1], _new_position.hash)
    # transfer borrow_currency_current_value from borrower to this address
    token_transfer: bool = ERC20(_new_position.borrow_currency_address).transferFrom(
        _new_position.borrower,
        self,
        _new_position.borrow_currency_current_value
    )
    assert token_transfer
    # transfer lend_currency_filled_value from lender to borrower
    token_transfer = ERC20(_new_position.lend_currency_address).transferFrom(
        _new_position.lender,
        _new_position.borrower,
        _new_position.lend_currency_filled_value
    )
    assert token_transfer
    # transfer monitoring_fee from lender to wrangler
    token_transfer = ERC20(self.protocol_token_address).transferFrom(
        _new_position.lender,
        _new_position.wrangler,
        _new_position.monitoring_fee
    )
    assert token_transfer
    # notify wrangler that a position has been opened
    log.PositionUpdateNotification(_new_position.wrangler, _new_position.hash, "status", self.POSITION_STATUS_OPEN)
    # unlock position_non_reentrant after loan creation
    self.unlock_position(_new_position.hash)


# external functions
@public
def topup_position(_position_hash: bytes32, _borrow_currency_increment: uint256) -> bool:
    existing_position: Position = self.positions[_position_hash]
    # confirm sender is borrower
    assert msg.sender == existing_position.borrower
    # confirm position has not expired yet
    assert existing_position.expires_at >= block.timestamp
    # confirm position is still active
    assert existing_position.status == self.POSITION_STATUS_OPEN
    # lock position_non_reentrant before topup
    self.lock_position(_position_hash)
    # perform topup
    existing_position.borrow_currency_current_value += _borrow_currency_increment
    self.positions[_position_hash] = existing_position
    # transfer borrow_currency_current_value from borrower to this address
    token_transfer: bool = ERC20(existing_position.borrow_currency_address).transferFrom(
        existing_position.borrower,
        self,
        _borrow_currency_increment
    )
    assert token_transfer
    # Notify wrangler that a position has been topped up
    log.PositionUpdateNotification(existing_position.wrangler, _position_hash, "borrow_currency_value", self.POSITION_TOPPED_UP)
    # unlock position_non_reentrant after topup
    self.unlock_position(_position_hash)

    return True


@public
def liquidate_position(_position_hash: bytes32) -> bool:
    existing_position: Position = self.positions[_position_hash]
    # confirm position has expired
    assert existing_position.expires_at < block.timestamp
    # confirm sender is lender or wrangler
    assert ((msg.sender == existing_position.wrangler) or (msg.sender == existing_position.lender))
    # confirm position is still active
    assert existing_position.status == self.POSITION_STATUS_OPEN
    # lock position_non_reentrant before liquidation
    self.lock_position(_position_hash)
    # perform liquidation
    existing_position.status = self.POSITION_STATUS_LIQUIDATED
    self.positions[_position_hash] = existing_position
    self.remove_position(_position_hash)
    # transfer borrow_currency_current_value from this address to the sender
    token_transfer: bool = ERC20(existing_position.borrow_currency_address).transfer(
        msg.sender,
        existing_position.borrow_currency_current_value
    )
    assert token_transfer
    # notify wrangler that a position has been liquidated
    log.PositionUpdateNotification(existing_position.wrangler, _position_hash, "status", self.POSITION_STATUS_LIQUIDATED)
    # unlock position_non_reentrant after liquidation
    self.unlock_position(_position_hash)

    return True


@public
def close_position(_position_hash: bytes32) -> bool:
    existing_position: Position = self.positions[_position_hash]
    # confirm sender is borrower
    assert msg.sender == existing_position.borrower
    # confirm position has not expired yet
    assert existing_position.expires_at >= block.timestamp
    # confirm position is still active
    assert existing_position.status == self.POSITION_STATUS_OPEN
    # lock position_non_reentrant before closure
    self.lock_position(_position_hash)
    # perform closure
    existing_position.status = self.POSITION_STATUS_CLOSED
    self.positions[_position_hash] = existing_position
    self.remove_position(_position_hash)
    # transfer lend_currency_owed_value from borrower to lender
    token_transfer: bool = ERC20(existing_position.lend_currency_address).transferFrom(
        existing_position.borrower,
        existing_position.lender,
        existing_position.lend_currency_owed_value
    )
    assert token_transfer
    # transfer borrow_currency_current_value from this address to borrower
    token_transfer = ERC20(existing_position.borrow_currency_address).transfer(
        existing_position.borrower,
        existing_position.borrow_currency_current_value
    )
    assert token_transfer
    # Notify wrangler that a position has been closed
    log.PositionUpdateNotification(existing_position.wrangler, _position_hash, "status", self.POSITION_STATUS_CLOSED)
    # unlock position_non_reentrant after closure
    self.unlock_position(_position_hash)

    return True


@public
def fill_kernel(
        _addresses: address[6],
        # _addresses: lender, borrower, relayer, wrangler, collateralToken, loanToken
        _values: uint256[7],
        # _values: collateralAmount, loanAmountOffered, relayerFeeLST, monitoringFeeLST, rolloverFeeLST, closureFeeLST, loanAmountFilled
        _nonce: uint256,
        _kernel_daily_interest_rate: uint256,
        _is_creator_lender: bool,
        _timestamps: timestamp[2],
        # kernel_expires_at, wrangler_approval_expires_at
        _position_duration_in_seconds: timedelta,
        # loanDuration
        _kernel_creator_salt: bytes32,
        _sig_data_kernel_creator: bytes[65],
        _sig_data_wrangler: bytes[65]
        # v, r, s of kernel_creator and wrangler
        ) -> bool:
    # validate _lender is not empty
    assert _addresses[0] != ZERO_ADDRESS
    # validate _borrower is not empty
    assert _addresses[1] != ZERO_ADDRESS
    _kernel_creator: address = _addresses[1]
    _kernel: Kernel = Kernel({
        lender: ZERO_ADDRESS,
        borrower: _addresses[1],
        relayer: _addresses[2],
        wrangler: _addresses[3],
        borrow_currency_address: _addresses[4],
        lend_currency_address: _addresses[5],
        lend_currency_offered_value: _values[1],
        relayer_fee: _values[2],
        monitoring_fee: _values[3],
        rollover_fee: _values[4],
        closure_fee: _values[5],
        salt: _kernel_creator_salt,
        expires_at: _timestamps[0],
        daily_interest_rate: _kernel_daily_interest_rate,
        position_duration_in_seconds: _position_duration_in_seconds
    })
    if _is_creator_lender:
        _kernel_creator = _addresses[0]
        _kernel.lender = _addresses[0]
        _kernel.borrower = ZERO_ADDRESS
    # It's OK if _relayer is empty
    # validate _wrangler is not empty
    assert _kernel.wrangler != ZERO_ADDRESS
    # validate _collateralToken is a contract address
    assert self.supported_tokens[_kernel.borrow_currency_address]
    # validate _loanToken is a contract address
    assert self.supported_tokens[_kernel.lend_currency_address]
    # validate loan amounts
    assert as_unitless_number(_values[0]) > 0
    assert as_unitless_number(_kernel.lend_currency_offered_value) > 0
    assert as_unitless_number(_values[6]) > 0
    # validate asked and offered expiry timestamps
    assert _kernel.expires_at > block.timestamp
    # validate daily interest rate on Kernel is greater than 0
    assert as_unitless_number(_kernel.daily_interest_rate) > 0
    # compute hash of kernel
    _k_hash: bytes32 = self.kernel_hash(
        [_kernel.lender, _kernel.borrower, _kernel.relayer, _kernel.wrangler,
        _kernel.borrow_currency_address, _kernel.lend_currency_address],
        [_kernel.lend_currency_offered_value,
        _kernel.relayer_fee, _kernel.monitoring_fee, _kernel.rollover_fee, _kernel.closure_fee],
        _kernel.expires_at, _kernel.salt, _kernel.daily_interest_rate, _kernel.position_duration_in_seconds)
    # validate kernel_creator's signature
    assert self.is_signer(_kernel_creator, _k_hash, _sig_data_kernel_creator)
    # validate loan amount to be filled
    assert as_unitless_number(_kernel.lend_currency_offered_value) - as_unitless_number(self.filled_or_cancelled_loan_amount(_k_hash)) >= as_unitless_number(_values[6])
    # fill offer with lending currency
    self.kernels_filled[_k_hash] += _values[6]
    # open position
    self.open_position(
        _kernel_creator, _addresses, _values,
        _nonce, _kernel_daily_interest_rate,
        _position_duration_in_seconds, _timestamps[1], _sig_data_wrangler
    )
    # transfer relayerFeeLST from kernel creator to relayer
    if (_kernel.relayer != ZERO_ADDRESS) and (as_unitless_number(_kernel.relayer_fee) > 0):
        token_transfer: bool = ERC20(self.protocol_token_address).transferFrom(
            _kernel_creator,
            _kernel.relayer,
            _kernel.relayer_fee
        )
        assert token_transfer

    return True


@public
def cancel_kernel(
        _addresses: address[6], _values: uint256[5],
        _kernel_expires: timestamp, _kernel_creator_salt: bytes32,
        _kernel_daily_interest_rate: uint256, _position_duration_in_seconds: timedelta,
        _sig_data: bytes[65],
        _lend_currency_cancel_value: uint256) -> bool:
    # compute kernel hash from inputs
    _kernel: Kernel = Kernel({
        lender: _addresses[0],
        borrower: _addresses[1],
        relayer: _addresses[2],
        wrangler: _addresses[3],
        borrow_currency_address: _addresses[4],
        lend_currency_address: _addresses[5],
        lend_currency_offered_value: _values[0],
        relayer_fee: _values[1],
        monitoring_fee: _values[2],
        rollover_fee: _values[3],
        closure_fee: _values[4],
        salt: _kernel_creator_salt,
        expires_at: _kernel_expires,
        daily_interest_rate: _kernel_daily_interest_rate,
        position_duration_in_seconds: _position_duration_in_seconds
    })
    _k_hash: bytes32 = self.kernel_hash(
        [_kernel.lender, _kernel.borrower, _kernel.relayer, _kernel.wrangler,
        _kernel.borrow_currency_address, _kernel.lend_currency_address],
        [_kernel.lend_currency_offered_value,
        _kernel.relayer_fee, _kernel.monitoring_fee, _kernel.rollover_fee, _kernel.closure_fee],
        _kernel.expires_at, _kernel.salt, _kernel.daily_interest_rate, _kernel.position_duration_in_seconds)
    # verify sender is kernel creator
    assert self.is_signer(msg.sender, _k_hash, _sig_data)
    # verify sanity of offered and cancellation amounts
    assert as_unitless_number(_kernel.lend_currency_offered_value) > 0
    assert as_unitless_number(_lend_currency_cancel_value) > 0
    # verify cancellation amount does not exceed remaining loan amount to be filled
    assert as_unitless_number(_kernel.lend_currency_offered_value) - self.filled_or_cancelled_loan_amount(_k_hash) >= as_unitless_number(_lend_currency_cancel_value)
    self.kernels_cancelled[_k_hash] += _lend_currency_cancel_value

    return True
