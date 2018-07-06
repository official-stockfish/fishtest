import datetime
import sys

def worker_stats(result, line):
    # Parse line like this (wins and losses):
    # Finished game 35 (New-1fd2593 vs Base-3d6995e): 0-1 {Black wins by adjudication}
    if 'White' or 'Black' in line:
        w_segm = line.split('vs')
        if 'New' in w_segm[0]:
            if 'White' in line:
                if 'adjudication' in line:
                    result['details']['win_a'] += 1
                elif 'mated' in line:
                    result['details']['loss_m'] += 1
                elif 'time' in line:
                    result['details']['loss_t'] += 1
                elif 'illegal' in line:
                    result['details']['loss_i'] += 1
            elif 'Black' in line:
                if 'adjudication' in line:
                    result['details']['loss_a'] += 1
                elif 'mated' in line:
                    result['details']['win_m'] += 1
                elif 'time' in line:
                    result['details']['win_t'] += 1
                elif 'illegal' in line:
                    result['details']['win_i'] += 1
        elif 'Base' in w_segm[0]:
            if 'White' in line:
                if 'adjudication' in line:
                    result['details']['loss_a'] += 1
                elif 'mated' in line:
                    result['details']['win_m'] += 1
                elif 'time' in line:
                    result['details']['win_t'] += 1
                elif 'illegal' in line:
                    result['details']['win_i'] += 1
            elif 'Black' in line:
                if 'adjudication' in line:
                    result['details']['win_a'] += 1
                elif 'mated' in line:
                    result['details']['loss_m'] += 1
                elif 'time' in line:
                    result['details']['loss_t'] += 1
                elif 'illegal' in line:
                    result['details']['loss_i'] += 1

    # Parse line like this (draws):
    # Finished game 73 (stockfish vs base): 1/2-1/2 {Draw by adjudication}
    if 'Finished' in line:
        segm = line.split('{')
        segm = segm[1]
        segm = segm[:-1]
        if 'Draw by adjudication' in segm:
            result['details']['draw_a'] += 1
        elif 'Draw by 3-fold repetition' in segm:
            result['details']['draw_r'] += 1
        elif 'Draw by insufficient mating material' in segm:
            result['details']['draw_i'] += 1
        elif 'Draw by fifty moves rule' in segm:
            result['details']['draw_f'] += 1
        elif 'Draw by stalemate' in segm:
            result['details']['draw_s'] += 1

def print_details(result):
    total_w = result['details']['win_a'] + result['details']['win_m'] + result['details']['win_t'] + result['details']['win_i']
    total_l = result['details']['loss_a'] + result['details']['loss_m'] + result['details']['loss_t'] + result['details']['loss_i']
    total_d = result['details']['draw_a'] + result['details']['draw_r'] + result['details']['draw_i'] + result['details']['draw_f'] + result['details']['draw_s']
    total_wld = total_w + total_l + total_d
    
    # Print result to output
    if total_wld > 0:
        print('Total: {0} W: {1} L: {2} D: {3}'.format(total_wld, total_w, total_l, total_d))
        print('W[{0}%]: a={1} m={2} t={3} i={4}'.format("%.1f" % ((float(total_w) / total_wld)*100), result['details']['win_a'], result['details']['win_m'], result['details']['win_t'], result['details']['win_i']))
        print('L[{0}%]: a={1} m={2} t={3} i={4}'.format("%.1f" % ((float(total_l) / total_wld)*100), result['details']['loss_a'], result['details']['loss_m'], result['details']['loss_t'], result['details']['loss_i']))
        print('D[{0}%]: a={1} r={2} i={3} f={4} s={5}'.format("%.1f" % ((float(total_d) / total_wld)*100), result['details']['draw_a'], result['details']['draw_r'], result['details']['draw_i'], result['details']['draw_f'], result['details']['draw_s']))
