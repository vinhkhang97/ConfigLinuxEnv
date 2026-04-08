### Reset group path
reset_path_group -all
resetPathGroupOptions
### Basic group path
group_path -name reg2reg -from [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]                     -to [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]
group_path -name reg2icg -from [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]                     -to [filter_collection [all_registers] "is_integrated_clock_gating_cell == true"]
group_path -name reg2mem -from [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]                     -to [filter_collection [all_registers -macros] "is_memory_cell == true"]
group_path -name mem2reg -from [filter_collection [all_registers -macros] "is_memory_cell == true"]                              -to [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]
group_path -name mem2mem -from [filter_collection [all_registers -macros] "is_memory_cell == true"]                              -to [filter_collection [all_registers -macros] "is_memory_cell == true"]
group_path -name reg2out -from [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]                     -to [all_outputs]
group_path -name in2reg  -from [all_inputs -no_clocks]                                                                           -to [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]
group_path -name in2out  -from [all_inputs -no_clocks]                                                                           -to [all_outputs]
group_path -name in2icg  -from [all_inputs -no_clocks]                                                                           -to [filter_collection [all_registers] "is_integrated_clock_gating_cell == true"]
###########group TOP################
#group_path -name reg2out_reg2top -from [filter_collection [all_registers] "is_integrated_clock_gating_cell != true"]             -to [get_ports {ahbdec2vi200_hreadyout awaddr_s0_vi200_wo[16] awsize_s0_vi200_wo[2] dvp_out0_val dvp_out1_val dvp_out2_val vi200_ch14_bwl_urgent vi200_ch12_bwl_urgent ahbdec2vi200_hreadyo
#group_path -name in2reg_top2reg -from [get_ports {ahbdec2vi200_haddr[*] ahbdec2vi200_haddr[*] csi_muxed_ipi1_color_depth[*] rst_csi_rx0_n rst_csi_rx1_n rst_csi_rx2_n rst_csi_rx3_n rst_data_bus_vi200_n rst_vi200_ahb_n rst_vi200_axi_n rst_vi200_n rst_vi_ipi0_n rtc_64bit_value[*] vi200_ch0_pwm_int vi200_ch10_pwm_int v
#group_path -name in2icg_top2reg -from [get_ports {ahbdec2vi200_hready ahbdec2vi200_htrans[1] ahbdec2vi200_hsel}]                 -to [filter_collection [all_registers] "is_integrated_clock_gating_cell == true"]
### Set path group options
setPathGroupOptions mem2reg -effortLevel high -weight 9
setPathGroupOptions mem2mem -effortLevel high -weight 9
setPathGroupOptions reg2reg -effortLevel high -weight 9
setPathGroupOptions reg2icg -effortLevel high -weight 8
setPathGroupOptions reg2mem -effortLevel high -weight 9
setPathGroupOptions reg2out -effortLevel  low -weight 4
setPathGroupOptions in2reg  -effortLevel  low -weight 4
setPathGroupOptions in2out  -effortLevel  low -weight 4
setPathGroupOptions in2icg  -effortLevel high -weight 8
setPathGroupOptions default -effortLevel high
#setPathGroupOptions reg2out_reg2top -effortLevel high -weight 8 -late -slackAdjustment -0.15
#setPathGroupOptions in2reg_top2reg  -effortLevel high -weight 9 -late -slackAdjustment -0.2
#setPathGroupOptions in2icg_top2reg  -effortLevel high -weight 9 -late -slackAdjustment -0.1
#___________________________________________
### Set adjustment for path group
#setPathGroupOptions reg2reg -late -slackAdjustment 1.5
reportPathGroupOptions
