/*
  This program computes passing probabilities and expected running times for SPRT tests.
  See http://hardy.uhasselt.be/Fishtest/sprta.pdf for more information.
*/

const nelo_divided_by_nt = 800 / Math.log(10);

function L(x) {
  return 1 / (1 + Math.pow(10, -x / 400));
}

function Linv(x) {
  return -400 * Math.log10(1 / x - 1);
}

function PT(LA, LB, h) {
  // Universal functions
  let P, T;
  if (Math.abs(h * (LA - LB)) < 1e-6) {
    // avoid division by zero
    P = -LA / (LB - LA);
    T = -LA * LB;
  } else {
    const exp_a = Math.exp(-h * LA);
    const exp_b = Math.exp(-h * LB);
    P = (1 - exp_a) / (exp_b - exp_a);
    T = (2 / h) * (LB * P + LA * (1 - P));
  }
  return [P, T];
}

function Sprt(alpha, beta, elo0, elo1, draw_ratio, rms_bias, elo_model) {
  const rms_bias_score = L(rms_bias) - 0.5;
  const variance3 = (1 - draw_ratio) / 4.0;
  this.variance = variance3 - Math.pow(rms_bias_score, 2);
  if (this.variance <= 0) {
    return;
  }
  if (elo_model == "Logistic") {
    this.elo0 = elo0;
    this.elo1 = elo1;
    this.score0 = L(elo0);
    this.score1 = L(elo1);
  } else {
    // Assume "Normalized"
    const nt0 = elo0 / nelo_divided_by_nt;
    const nt1 = elo1 / nelo_divided_by_nt;
    const sigma = Math.sqrt(this.variance);
    this.score0 = nt0 * sigma + 0.5;
    this.score1 = nt1 * sigma + 0.5;
    this.elo0 = Linv(this.score0);
    this.elo1 = Linv(this.score1);
  }
  this.w2 = Math.pow(this.score1 - this.score0, 2) / this.variance;
  this.LA = Math.log(beta / (1 - alpha));
  this.LB = Math.log((1 - beta) / alpha);
  this.characteristics = function (elo) {
    const score = L(elo);
    const h =
      (2 * score - (this.score0 + this.score1)) / (this.score1 - this.score0);
    const PT_ = PT(this.LA, this.LB, h);
    return [PT_[0], PT_[1] / this.w2];
  };
}
