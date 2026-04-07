#!usr/bin/tclsh 

proc innovusFara {infile outfile} {
    set data [open "|cat $infile" "r"] 
    set ofp [open $outfile "w"]
    set flag 0
    set flagDataCell 0
    set totalCell 0
    set range0 0
    set range1 -0.1
    set range2 -0.2
    set range3 -0.3
    set range4 -0.4
    set i1 0; set i2 0; set i0 0; set i3 0; set i4 0; set i5 0
    puts $ofp "Startpoint, Clock Start, Endpoint, Clock End, Phase Shift, Uncertainty, Slack, launchDelay, captureDelay, dataDelay, delaybPoint, skew, levelCellLogic, levelBuf"
    while {[gets $data line] != -1} {
        if {[regexp -all {Endpoint:} $line]} {
            set ePoint [lindex $line 1]
            set eClk [regsub -all {\'} [lindex $line end] ""]
        }
        if {[regexp -all {Beginpoint:} $line]} {
            set bPoint [lindex $line 1]
            set bClk [regsub -all {\'} [lindex $line end] ""]
        }
        if {[regexp -all {Phase Shift} $line]} {
            set pShift [lindex $line end]
        }
        if {[regexp -all {Uncertainty} $line]} {
            set uncer [lindex $line end]
        }
        if {[regexp -all {Slack Time} $line]} {
            set slack [lindex $line 3]
            if {$slack >= $range0} {incr i0}    
            if {($slack < $range0) && ($slack >= $range1)} {incr i1} 
            if {($slack < $range1) && ($slack >= $range2)} {incr i2} 
            if {($slack < $range2) && ($slack >= $range3)} {incr i3} 
            if {($slack < $range3) && ($slack >= $range4)} {incr i4} 
            if {$slack < $range4} {incr i5} 
        }
        if {[regexp -all {Beginpoint Arrival Time} $line] && ($flag == 0)} {
            set beginTime [lindex $line 4]
            set flag 1
        }
        if {$flag == 1} {
            if {$bPoint == [lindex $line 0]} {
                set sDataTime [lindex $line 10]
                set delaybPoint [lindex $line 7]
                set launchDelay [expr $sDataTime - $delaybPoint - $beginTime]
                set flagDataCell 1 
                set totalCell 0
                set totalBuf 0
            }
            if {$ePoint == [lindex $line 0]} {
                set eDataTime [lindex $line 10]
                set dataDelay [expr $eDataTime - $sDataTime]
                set flag 2
                set flagDataCell 0
            }
            if {$flagDataCell} {
                incr totalCell
                if {[regexp -all {BUF} [lindex $line 1]] || [regexp -all {INV} [lindex $line 1]]} {
                    incr totalBuf
                }
            }
        }   
        if {[regexp -all {Beginpoint Arrival Time} $line] && ($flag == 2)} {
            set beginCapture [lindex $line 4]
            regexp -all {(.*)/([^/]*)} $ePoint full p1 p2
            set flag 3
        }
        if {$flag == 3} {
            if {[regexp -all "$p1" $line]} {
                set endCapture [lindex $line 10]
                set captureDelay [expr $endCapture -$beginCapture]
                set skew [expr $captureDelay - $launchDelay]
            }
        }
        #puts $flag
        if {[regexp -all {(Path)\s+([^A-Z][0-9]*)} $line] && ($flag == 3)} {
            set levelCell [expr ($totalCell + 1)/ 2 -1]
            set levelBuf [expr $totalBuf / 2]
            puts $ofp "$bPoint, $bClk, $ePoint, $eClk, $pShift, $uncer, $slack, $launchDelay, $captureDelay, $dataDelay, $delaybPoint, $skew, $levelCell, $levelBuf"
            set flag 0
        }
    }
    exec mv $outfile $outfile.csv
    close $data
    close $ofp
    puts "------------Summary slack-------------"
    puts "       Slack >=  $range0 : $i0"
    puts "   $range0 > Slack >= $range1 : $i1"
    puts "$range1 > Slack >= $range2 : $i2"
    puts "$range2 > Slack >= $range3 : $i3"
    puts "$range3 > Slack >= $range4 : $i4"
    puts "$range4 > Slack : $i5"
    puts "####### Done summary timing #######"
    puts "### Please check timing in file $outfile.csv by cmd \" libreoffice7.3 $outfile.csv \" ###"
}

eval "innovusFara $argv"
