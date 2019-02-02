// helpers
const mineTx = require("./helpers/mineTx.js");
const delay = require("./helpers/delay.js");
// contracts
var ERC20 = artifacts.require('ERC20.vyper'),
  Protocol = artifacts.require('protocol.vyper');
// provider
const Web3 = require('web3');
const web3 = new Web3(new Web3.providers.HttpProvider("http://127.0.0.1:8545"))

contract("Protocol", function (addresses) {

  beforeEach(async function () {
    this.ZERO_ADDRESS = 0x0000000000000000000000000000000000000000;
    this.protocolToken = await ERC20.new("Lendroid Support Token", "LST", 18, 12000000000);
    this.LendToken = await ERC20.new("Test Lend Token", "TLT", 18, 1000000000);
    this.BorrowToken = await ERC20.new("Test Borrow Token", "TBT", 18, 1000000000);
    this.protocolContract = await Protocol.new(this.protocolToken.address);
    this.lender = addresses[1];
    this.borrower = addresses[2];
    this.relayer = addresses[3];
    this.wrangler = addresses[4];
    //// kernel terms
    // uint256 values
    this.kernel_daily_interest_rate = 10
    // timedelta values
    this.kernel_position_duration_in_seconds = 5
    this.wrangler_approval_duration_in_seconds = 5 * 60
    // wei values
    this.kernel_lending_currency_maximum_value = web3._extend.utils.toWei('40', 'ether')
    this.kernel_relayer_fee = web3._extend.utils.toWei('10', 'ether')
    this.kernel_monitoring_fee = web3._extend.utils.toWei('10', 'ether')
    this.kernel_rollover_fee = web3._extend.utils.toWei('10', 'ether')
    this.kernel_closure_fee = web3._extend.utils.toWei('10', 'ether')
    // timestamp values
    this.kernel_expires_at = web3.eth.getBlock(web3.eth.blockNumber).timestamp + 86400*2
    // bytes32 values
    this.kernel_creator_salt = '0x92c0b12fa215396ed0867a9a871aee1a17657643000000000000000000000000'
    // position terms
    this.position_lending_currency_fill_value = web3._extend.utils.toWei('30', 'ether')
    this.position_borrow_currency_fill_value = web3._extend.utils.toWei('3', 'ether')
    this.position_lending_currency_owed_value = web3._extend.utils.toWei('30', 'ether')
    // open position
    let tx = this.protocolToken.mint(this.lender, web3._extend.utils.toWei('100', 'ether'), {from: addresses[0]})
    await mineTx(tx);
    tx = this.protocolToken.approve(this.protocolContract.address, web3._extend.utils.toWei('100', 'ether'), {from: this.lender})
    await mineTx(tx);
    // set allowance from lender to protocol contract for loan transfer
    tx = this.LendToken.mint(this.lender, web3._extend.utils.toWei('40', 'ether'), {from: addresses[0]})
    await mineTx(tx);
    tx = this.LendToken.approve(this.protocolContract.address, web3._extend.utils.toWei('40', 'ether'), {from: this.lender})
    await mineTx(tx);
    // set allowance from borrower to protocol contract for collateral transfer
    tx = this.BorrowToken.mint(this.borrower, web3._extend.utils.toWei('5', 'ether'), {from: addresses[0]})
    await mineTx(tx);
    tx = this.BorrowToken.approve(this.protocolContract.address, web3._extend.utils.toWei('5', 'ether'), {from: this.borrower})
    await mineTx(tx);
    // Approve wrangler as protocol owner
    tx = this.protocolContract.set_wrangler_status(this.wrangler, true, {from:addresses[0]});
    await mineTx(tx);
    // Sign kernel hash as lender
    let kernel_hash = await this.protocolContract.kernel_hash(
      [
        this.lender, this.ZERO_ADDRESS, this.relayer, this.wrangler, this.BorrowToken.address, this.LendToken.address
      ],
      [
        this.kernel_lending_currency_maximum_value,
        this.kernel_relayer_fee, this.kernel_monitoring_fee, this.kernel_rollover_fee, this.kernel_closure_fee
      ],
      this.kernel_expires_at, this.kernel_creator_salt,
      this.kernel_daily_interest_rate, this.kernel_position_duration_in_seconds
    )
    let _kernel_creator_signature = web3.eth.sign(this.lender, kernel_hash)
    _kernel_creator_signature = _kernel_creator_signature.substr(2)
    // Sign position hash as wrangler
    let _nonce = '1';
    this.position_hash = await this.protocolContract.position_hash(
      [
        this.lender, this.lender, this.borrower, this.relayer, this.wrangler, this.BorrowToken.address, this.LendToken.address
      ],
      [
        this.position_borrow_currency_fill_value, this.kernel_lending_currency_maximum_value,
        this.kernel_relayer_fee, this.kernel_monitoring_fee, this.kernel_rollover_fee, this.kernel_closure_fee,
        this.position_lending_currency_fill_value
      ],
      this.position_lending_currency_owed_value,
      _nonce
    )
    let _wrangler_approval_expiry_timestamp = web3.eth.getBlock(web3.eth.blockNumber).timestamp + this.wrangler_approval_duration_in_seconds
    let _wrangler_signature = web3.eth.sign(this.wrangler, this.position_hash)
    _wrangler_signature = _wrangler_signature.substr(2)
    // prepare inputs
    let _is_creator_lender = true;
    // do call
    tx = await this.protocolContract.fill_kernel(
      [
        this.lender, this.borrower, this.relayer, this.wrangler, this.BorrowToken.address, this.LendToken.address
      ],
      [
        this.position_borrow_currency_fill_value, this.kernel_lending_currency_maximum_value,
        this.kernel_relayer_fee, this.kernel_monitoring_fee, this.kernel_rollover_fee, this.kernel_closure_fee,
        this.position_lending_currency_fill_value
      ],
      _nonce,
      this.kernel_daily_interest_rate,
      _is_creator_lender,
      [
        this.kernel_expires_at, _wrangler_approval_expiry_timestamp
      ],
      this.kernel_position_duration_in_seconds,
      this.kernel_creator_salt,
      [
        [
          `${_kernel_creator_signature.slice(128, 130)}` === '00' ? web3._extend.utils.toBigNumber(27) : web3._extend.utils.toBigNumber(28),
          web3._extend.utils.toBigNumber(`0x${_kernel_creator_signature.slice(0, 64)}`),
          web3._extend.utils.toBigNumber(`0x${_kernel_creator_signature.slice(64, 128)}`)
        ],
        [
          `${_wrangler_signature.slice(128, 130)}` === '00' ? web3._extend.utils.toBigNumber(27) : web3._extend.utils.toBigNumber(28),
          web3._extend.utils.toBigNumber(`0x${_wrangler_signature.slice(0, 64)}`),
          web3._extend.utils.toBigNumber(`0x${_wrangler_signature.slice(64, 128)}`)
        ],
      ],
      {from: addresses[0]}
    );
    await mineTx(tx);
    this.position_index = await this.protocolContract.borrow_positions_count(this.borrower)
    this.position_hash = await this.protocolContract.borrow_positions(this.borrower, this.position_index)
    this.position = await this.protocolContract.position(this.position_hash)
  });


  it("liquidate_position should not work before position has expired", async function() {
    let errr = false
    try {
      await this.protocolContract.liquidate_position(this.position_hash, {from:this.lender});
    } catch (e) {
      errr = true
    }
    assert.isTrue(errr, 'lender should not be able to liquidate a position before position has expired')
    errr = false
    try {
      await this.protocolContract.liquidate_position(this.position_hash, {from:this.wrangler});
    } catch (e) {
      errr = true
    }
    assert.isTrue(errr, 'wrangler should not be able to liquidate a position before position has expired')
  });


  it("liquidate_position should be callable by lender", async function() {
    console.log(`Position expiry timestamp: ${this.position[6].toNumber()}`)
    while (web3.eth.getBlock(web3.eth.blockNumber).timestamp <= this.position[6].toNumber()) {
      console.log(`Current blocktimestamp: ${web3.eth.getBlock(web3.eth.blockNumber).timestamp}. Will check after 1s ...`)
      web3.currentProvider.send({
       jsonrpc: "2.0",
       method: "evm_mine",
       id: new Date().getTime()
      })
      await delay(5001)
    }
    console.log(`Current blocktimestamp: ${web3.eth.getBlock(web3.eth.blockNumber).timestamp}`)
    let errr = false
    try {
      await this.protocolContract.liquidate_position(this.position_hash, {from:this.lender});
    } catch (e) {
      errr = true
    }
    assert.isTrue(!errr, 'lender should be able to liquidate a position')
  });

  it("liquidate_position should be callable by wrangler", async function() {
    console.log(`Position expiry timestamp: ${this.position[6].toNumber()}`)
    while (web3.eth.getBlock(web3.eth.blockNumber).timestamp <= this.position[6].toNumber()) {
      console.log(`Current blocktimestamp: ${web3.eth.getBlock(web3.eth.blockNumber).timestamp}. Will check after 1s ...`)
      web3.currentProvider.send({
       jsonrpc: "2.0",
       method: "evm_mine",
       id: new Date().getTime()
      })
      await delay(5001)
    }
    console.log(`Current blocktimestamp: ${web3.eth.getBlock(web3.eth.blockNumber).timestamp}`)
    let errr = false
    try {
      await this.protocolContract.liquidate_position(this.position_hash, {from:this.wrangler});
    } catch (e) {
      errr = true
    }
    assert.isTrue(!errr, 'wrangler should be able to liquidate a position')
  });

  it("liquidate_position should not be callable by borrower", async function() {
    console.log(`Position expiry timestamp: ${this.position[6].toNumber()}`)
    while (web3.eth.getBlock(web3.eth.blockNumber).timestamp <= this.position[6].toNumber()) {
      console.log(`Current blocktimestamp: ${web3.eth.getBlock(web3.eth.blockNumber).timestamp}. Will check after 1s ...`)
      web3.currentProvider.send({
       jsonrpc: "2.0",
       method: "evm_mine",
       id: new Date().getTime()
      })
      await delay(5001)
    }
    console.log(`Current blocktimestamp: ${web3.eth.getBlock(web3.eth.blockNumber).timestamp}`)
    let errr = false
    try {
      await this.protocolContract.liquidate_position(this.position_hash, {from:this.borrower});
    } catch (e) {
      errr = true
    }
    assert.isTrue(errr, 'borrower should be able to close a position')
  });

});
