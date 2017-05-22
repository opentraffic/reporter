package org.opentraffic.reporter;

import java.util.Properties;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Option;
import org.apache.commons.cli.Options;
import org.apache.commons.cli.ParseException;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.processor.TopologyBuilder;

public class Reporter {
  
  public static CommandLine parse(String[] args) {
    Option bootstrap = new Option("b", "bootstrap", true, "Bootstrap servers config");
    bootstrap.setRequired(true);
    Option root_topic = new Option("r", "root-topic", true, "Root topic");
    root_topic.setRequired(true);
    Option leaf_topic = new Option("l", "leaf-topic", true, "Leaf topic");
    leaf_topic.setRequired(true);
    Option files = new Option("f", "files", true, "The files to produce from");
    files.setRequired(true);
    
    Options options = new Options();
    options.addOption(bootstrap);
    options.addOption(root_topic);
    options.addOption(leaf_topic);
    options.addOption(files);

    CommandLineParser parser = new DefaultParser();
    HelpFormatter formatter = new HelpFormatter();
    CommandLine cmd = null;

    try {
      cmd = parser.parse(options, args);
    }
    catch (ParseException e) {
      System.out.println(e.getMessage());
      formatter.printHelp("kafka-reporter", options);
      System.exit(1);
    }
    return cmd;
  }
  
  public static void main(String[] args) throws Exception {
    CommandLine cmd = parse(args);
    
    Properties props = new Properties();
    //for now lets just start streaming from the beginning instead of coming in mid stream
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    //some init
    props.put(StreamsConfig.APPLICATION_ID_CONFIG, "reporter");
    props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, cmd.getOptionValue("bootstrap"));
    props.put(StreamsConfig.KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass());
    props.put(StreamsConfig.VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass());

    //hook stuff together
    Point.Serder pointSerder = new Point.Serder();
    TopologyBuilder builder = new TopologyBuilder();
    
    //takes raw input from tnc and reformat the tnc format data into
    //a key of string type and a value of Point type
    builder.addSource("Source", new StringDeserializer(), new StringDeserializer(), cmd.getOptionValue("root-topic"));
    builder.addProcessor("Formatter", new KeyedFormattingProcessor(args), "Source");
    builder.addSink("KeyedPointsSink", "Points", new StringSerializer(), pointSerder.serializer(), "Formatter");
    
    //take batches of points for a given key (uuid) and when some threshold is met
    //send that batch of points off to the reporter to be matched and update the
    //batch according to how much of the batch was used in matching
    builder.addSource("KeyedPointsSource", new StringDeserializer(), pointSerder.deserializer(), "Points");
    builder.addProcessor("Batcher", new BatchingProcessor(args), "KeyedPointsSource");
    builder.addStateStore(BatchingProcessor.GetStore(), "Batcher");
    builder.addSink("Sink", cmd.getOptionValue("leaf-topic"), "Batcher");
    
    //start consuming
    PrintConsumer consumer = new PrintConsumer(cmd);
    consumer.setDaemon(true);
    consumer.start();
    
    //start the topology
    KafkaStreams streams = new KafkaStreams(builder, props);
    streams.start();
    
    //start producing
    FileProducer producer = new FileProducer(cmd);
    producer.start();
    producer.join();

    //done
    pointSerder.close();
    streams.close();
  }
}